"""Private local IPC worker. CUDA visibility is set by Popen before imports."""
import os
import sys
import traceback
from multiprocessing.connection import Connection


def main():
    connection = Connection(int(sys.argv[1]))
    cancel = Connection(int(sys.argv[2]))
    # Observe the API process, not the transient threadpool thread that launched
    # us (Linux PDEATHSIG follows that thread and can kill a valid idle session).
    import threading
    import time
    parent = int(os.environ['VSL_PARENT_PID'])
    if os.getppid() != parent:
        return

    def watch_parent():
        while True:
            time.sleep(2)
            if os.getppid() != parent:
                os._exit(0)

    threading.Thread(target=watch_parent, daemon=True, name='sam-parent-watch').start()
    from app.services.annotation_store import AnnotationStore
    from app.services.sam_service import SAMService
    initial = connection.recv()
    config = initial['config']
    config.sam_device = 'cuda:0'
    service = SAMService(config, AnnotationStore(config.projects_dir))

    serve(connection, cancel, service)


def serve(connection, cancel, service):
    """Local protocol kept separate from model initialization for CPU tests."""
    was_cancelled = False

    def cancelled():
        nonlocal was_cancelled
        while cancel.poll():
            was_cancelled = (cancel.recv() == request['request_id']) or was_cancelled
        return was_cancelled

    def frame(value):
        connection.send({'type': 'frame', 'value': value})

    try:
        while True:
            request = connection.recv()
            was_cancelled = False
            try:
                operation = request['operation']
                if operation not in {'start_video_session', 'segment_frame', 'propagate_in_video',
                                     'remove_object', 'reset_session'}:
                    raise ValueError('Unsupported worker operation')
                kwargs = request.get('kwargs', {})
                if operation == 'propagate_in_video':
                    kwargs.update(on_frame=frame, should_cancel=cancelled)
                value = getattr(service, operation)(*request.get('args', []), **kwargs)
                if service.backend_name() == 'mock':
                    raise RuntimeError(service.fallback_error() or 'Real SAM failed to load')
                connection.send({'type': 'result', 'value': value, 'backend': service.backend_name()})
            except Exception as exc:
                traceback.print_exc()
                connection.send({'type': 'error', 'detail': str(exc)})
    except (EOFError, BrokenPipeError):
        pass
    finally:
        connection.close()
        cancel.close()


if __name__ == '__main__':
    main()
