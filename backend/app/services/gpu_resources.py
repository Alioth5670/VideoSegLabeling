"""Conservative GPU discovery without importing torch or creating a CUDA context."""
import csv
import io
import subprocess


class GPUResourceError(RuntimeError):
    pass


def discover_gpus(config) -> list[dict]:
    def query(fields, kind='gpu'):
        result = subprocess.run(['nvidia-smi', f'--query-{kind}={fields}', '--format=csv,noheader,nounits'],
                                capture_output=True, text=True, timeout=5, check=True)
        return list(csv.reader(io.StringIO(result.stdout), skipinitialspace=True))

    try:
        rows = query('index,uuid,name,memory.total,memory.free,memory.used,utilization.gpu,mig.mode.current')
        occupied = {row[0].strip() for row in query('gpu_uuid,pid', 'compute-apps') if len(row) == 2}
        allowed = {item.strip() for item in config.sam_gpu_devices.split(',') if item.strip()}
        devices = []
        for row in rows:
            if len(row) != 8:
                raise ValueError('Unexpected nvidia-smi response')
            index, uid, name, total, free, used, utilization, mig = (value.strip() for value in row)
            if allowed and index not in allowed and uid not in allowed:
                continue
            # MIG partition scheduling is deliberately unsupported. Unknown
            # metrics fail closed instead of guessing whether a GPU is free.
            try:
                total, free, used, utilization = (int(value) for value in (total, free, used, utilization))
            except ValueError:
                continue
            idle = (mig != 'Enabled' and uid not in occupied and
                    free >= config.sam_gpu_min_free_mb and used <= config.sam_gpu_max_used_mb and
                    utilization <= config.sam_gpu_max_utilization)
            devices.append({'id': uid, 'index': int(index), 'label': f'GPU {index} · {name}',
                            'total_memory_mb': total, 'free_memory_mb': free, 'used_memory_mb': used,
                            'utilization': utilization, 'available': idle})
        return devices
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise GPUResourceError('无法可靠查询 GPU 空闲状态，请检查 nvidia-smi 和驱动。') from exc
