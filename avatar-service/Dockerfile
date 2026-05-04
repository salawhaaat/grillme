FROM python:3.10-slim

# System deps: ffmpeg for video, OpenCV runtime libs, unzip for model setup
# No C++ compiler needed — HQ version uses pre-built ONNX face detectors
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsm6 \
    libxext6 \
    libxrender1 \
    git \
    curl \
    unzip \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Clone wav2lip-onnx-HQ (code only; models mounted at runtime via /app/models)
RUN git clone --depth 1 https://github.com/instant-high/wav2lip-onnx-HQ /app/wav2lip

# Patch out the two interactive cv2.selectROI calls so the script runs headless.
# 1. In select_specific_face(): replace selectROI with full-image selection,
#    and skip the recognition step (use first detected face in the image).
# 2. In main (image path): replace crop selectROI with full-frame, skip select_specific_face.
RUN python3 - <<'PYEOF'
import re
path = "/app/wav2lip/inference_onnxModel.py"
src = open(path).read()

# --- Patch 1: select_specific_face ---
# Replace the entire function body so it returns the identity of the first face found
old_fn = r'def select_specific_face\(model, spec_img, size, crop_scale=1\.0\):.*?return target_id'
new_fn = '''def select_specific_face(model, spec_img, size, crop_scale=1.0):
\t# Headless patch: use entire image, pick first detected face automatically
\th, w = spec_img.shape[:-1]
\tbboxes, kpss = model.detect(spec_img, input_size=(320, 320), det_thresh=0.3)
\tif len(kpss) == 0:
\t\traise RuntimeError("No face detected in face image")
\ttarget_face, mat = get_cropped_head_256(spec_img, kpss[0], size=size, scale=crop_scale)
\ttarget_face = cv2.resize(target_face, (112, 112))
\ttarget_id = recognition(target_face)[0].flatten()
\treturn target_id'''
src = re.sub(old_fn, new_fn, src, flags=re.DOTALL)

# --- Patch 2: main image path — replace crop+selectROI block ---
# The block: roi = cv2.selectROI("Crop final video" ...
#             cropped_roi = ...
#             cv2.destroyAllWindows()
#             full_frames = [cropped_roi]
#             orig_h, orig_w = cropped_roi.shape[:-1]
#             target_id = select_specific_face(...)
old_crop = (
    r'roi = cv2\.selectROI\("Crop final video".*?cv2\.destroyAllWindows\(\)\s*'
    r'full_frames = \[cropped_roi\]\s*'
    r'orig_h, orig_w = cropped_roi\.shape\[:-1\]\s*'
    r'#\s*select specific face:\s*'
    r'target_id = select_specific_face\(.*?\)'
)
new_crop = (
    '# Headless patch: use full image, no GUI crop\n'
    '\t\tfull_frames = [orig_frame]\n'
    '\t\torig_h, orig_w = orig_frame.shape[:-1]\n'
    '\t\t# Headless patch: detect first face automatically\n'
    '\t\ttarget_id = select_specific_face(detector, orig_frame, 256, crop_scale=1)'
)
src = re.sub(old_crop, new_crop, src, flags=re.DOTALL)

open(path, "w").write(src)
print("Patch applied OK")
PYEOF

# Patch 3: ffmpeg.exe → ffmpeg (script was written for Windows, we run on Linux)
RUN sed -i 's/ffmpeg\.exe/ffmpeg/g' /app/wav2lip/inference_onnxModel.py

# Create the temp dir the inference script expects at its cwd
RUN mkdir -p /app/wav2lip/temp

# Python deps — install before copying app code for layer caching
COPY avatar-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# FastAPI service + entrypoint
COPY avatar-service/main.py .
COPY avatar-service/entrypoint.sh .
RUN chmod +x entrypoint.sh

# Default face image (overridden by local face.jpg if present)
RUN curl -fsSL \
    "https://create-images-results.d-id.com/DefaultPresenters/Noelle_f/image.png" \
    -o /app/face_default.jpg

# Use custom face image (Elon) — overrides the default
COPY avatar-service/face.jpg /app/face.jpg

# Bake models into the image (populated by ./download_models.sh before build)
COPY models/ /app/models/

EXPOSE 8080

ENTRYPOINT ["/app/entrypoint.sh"]
