# SAM3 Local Inspection

Date: 2026-05-06

## Summary

- Repository path: `sam3/`
- README: `sam3/README.md` exists.
- Examples: `sam3/examples/` exists, including `sam3_video_predictor_example.ipynb` and `sam3.1_video_predictor_example.ipynb`.
- Checkpoints in workspace: `sam3.pt` and `sam3.1_multiplex.pt`.
- Video segmentation: supported by `build_sam3_video_predictor`.
- Multi-object tracking: supported through the video predictor API.
- SAM 3.1 Object Multiplex: supported by `build_sam3_multiplex_video_predictor` and documented in `RELEASE_SAM3p1.md`.

## Interfaces Found

- `sam3/sam3/model_builder.py`
  - `build_sam3_video_predictor`
  - `build_sam3_multiplex_video_predictor`
  - `build_sam3_predictor`
- `sam3/sam3/model/sam3_base_predictor.py`
  - `handle_request`
  - `handle_stream_request`
  - `start_session`
  - `add_prompt`
  - `propagate_in_video`
  - `remove_object`
  - `reset_session`
  - `close_session`
- `sam3/sam3/model/sam3_video_predictor.py`
  - `Sam3VideoPredictor`
  - `Sam3VideoPredictorMultiGPU`
- `sam3/sam3/model/sam3_multiplex_video_predictor.py`
  - `Sam3MultiplexVideoPredictor`

## Official Request Shape

The official video predictor uses request dictionaries:

```python
response = predictor.handle_request({
    "type": "start_session",
    "resource_path": video_or_frames_path,
})
session_id = response["session_id"]

response = predictor.handle_request({
    "type": "add_prompt",
    "session_id": session_id,
    "frame_index": 0,
    "text": "person",
})

for output in predictor.handle_stream_request({
    "type": "propagate_in_video",
    "session_id": session_id,
}):
    ...
```

`add_prompt` accepts text, points, point labels, bounding boxes, box labels, and `obj_id` through the base predictor dispatch. The wrapper converts list prompts to tensors and forwards only parameters supported by the underlying model.

## Current Implementation Choice

Phase 1-4 uses `SAM_BACKEND=mock` by default. Real SAM3 loading is isolated in `backend/app/services/sam_service.py`, with recognized backends:

- `mock`
- `sam3_video`
- `sam3_multiplex_video`

The real model branches are deliberately not used for phase 4 frame segmentation because the project brief requires first validating the official API and completing the mock closed loop. Later phases should extend only `sam_service.py` for real SAM3 frame segmentation and multiplex propagation.
