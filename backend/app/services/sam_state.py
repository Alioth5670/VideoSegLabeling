"""Compatibility fixes for the checked-in SAM3.1 interactive tracker."""
from functools import wraps
from typing import Any


def preserve_prompt_cache(tracker: Any) -> bool:
    """Keep consolidated corrections when clearing nearby propagated memory.

    The local tracker's cleaner removes both kinds of non-conditioning outputs,
    but propagation assumes every consolidated-frame marker still has an output.
    Retain only these explicit corrections; ordinary propagated memory is cleared
    by the original implementation as before. Values are referenced, not copied.
    """
    original = getattr(tracker, '_clear_non_cond_mem_around_input', None)
    if not callable(original):
        return False
    if getattr(original, '_vsl_prompt_cache_guard', False):
        return True

    @wraps(original)
    def clear(inference_state: dict, frame_idx: int):
        key = 'non_cond_frame_outputs'
        protected = inference_state.get('consolidated_frame_inds', {}).get(key, set())
        mappings = [inference_state.get('output_dict', {}).get(key, {})]
        mappings.extend(output.get(key, {}) for output in inference_state.get('output_dict_per_obj', {}).values())
        saved = [(mapping, {frame: mapping[frame] for frame in protected if frame in mapping}) for mapping in mappings]
        try:
            return original(inference_state, frame_idx)
        finally:
            for mapping, outputs in saved:
                mapping.update(outputs)

    clear._vsl_prompt_cache_guard = True
    tracker._clear_non_cond_mem_around_input = clear
    return True


def align_multiplex_state_devices(state: Any) -> None:
    """Run mux/demux on the input device without moving offloaded cache tensors.

    SAM's transition matrices live on the tracker device, whereas cached pointers
    and memories may live on CPU. Borrow a small aligned matrix for each operation,
    restoring the state's original matrix even if the operation fails.
    """
    for name, matrix_name in (('mux', 'mux_matrix'), ('demux', 'demux_matrix')):
        original = getattr(state, name, None)
        if not callable(original) or getattr(original, '_vsl_mux_device_guard', False):
            continue

        def wrap(operation, attribute):
            @wraps(operation)
            def apply(x):
                matrix = getattr(state, attribute)
                if matrix.device == x.device and matrix.dtype == x.dtype:
                    return operation(x)
                aligned = matrix.to(device=x.device, dtype=x.dtype)
                setattr(state, attribute, aligned)
                try:
                    return operation(x)
                finally:
                    setattr(state, attribute, matrix)
            apply._vsl_mux_device_guard = True
            return apply

        setattr(state, name, wrap(original, matrix_name))


def align_multiplex_devices(tracker: Any) -> bool:
    controller = getattr(tracker, 'multiplex_controller', None)
    original = getattr(controller, 'get_state', None)
    if not callable(original):
        return False
    if getattr(original, '_vsl_mux_device_guard', False):
        return True

    @wraps(original)
    def get_state(*args, **kwargs):
        state = original(*args, **kwargs)
        align_multiplex_state_devices(state)
        return state

    get_state._vsl_mux_device_guard = True
    controller.get_state = get_state
    return True
