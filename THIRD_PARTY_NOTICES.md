# Third-Party Notices

VideoSegLabeling is licensed under Apache-2.0.

SAM3 is referenced as a Git submodule at `sam3/` and is governed by Meta's SAM License. SAM3 trained model weights, checkpoints, and other SAM Materials are not committed to this repository or included in release packages. If you use SAM3 with this project, you are responsible for complying with Meta's SAM License.

The application can be configured to use a local SAM3 checkout and local checkpoints through:

```env
SAM_REPO_PATH=./sam3
SAM_CHECKPOINT_PATH=./checkpoints/sam3.pt
SAM31_CHECKPOINT_PATH=./checkpoints/sam3.1_multiplex.pt
```

Python and JavaScript dependencies are installed from their upstream package registries and remain under their respective licenses.
