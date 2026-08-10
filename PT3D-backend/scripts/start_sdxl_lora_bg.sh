#!/usr/bin/env bash
set -euo pipefail

# Start SDXL LoRA training in the background on a Linux GPU host.
# This wraps Hugging Face Diffusers' official SDXL LoRA training script.
#
# Required:
#   - diffusers repo cloned on the GPU host
#   - accelerate installed
#   - either DATASET_NAME or TRAIN_DATA_DIR set
#
# Example:
#   export DIFFUSERS_DIR=/root/diffusers
#   export TRAIN_DATA_DIR=/root/datasets/products-props
#   export OUTPUT_ROOT=/root/training/sdxl-lora
#   bash PT3-backend/scripts/start_sdxl_lora_bg.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

RUN_NAME="${RUN_NAME:-sdxl-lora-$(date +%Y%m%d-%H%M%S)}"
OUTPUT_ROOT="${OUTPUT_ROOT:-/root/training/sdxl-lora}"
RUNS_DIR="${RUNS_DIR:-$OUTPUT_ROOT/runs}"
LOG_DIR="${LOG_DIR:-$OUTPUT_ROOT/logs}"
OUTPUT_DIR="${OUTPUT_DIR:-$RUNS_DIR/$RUN_NAME}"
LOG_FILE="${LOG_FILE:-$LOG_DIR/$RUN_NAME.log}"
PID_FILE="${PID_FILE:-$LOG_DIR/$RUN_NAME.pid}"
COMMAND_FILE="${COMMAND_FILE:-$LOG_DIR/$RUN_NAME.command.sh}"

DIFFUSERS_DIR="${DIFFUSERS_DIR:-/root/diffusers}"
TRAIN_SCRIPT="${TRAIN_SCRIPT:-$DIFFUSERS_DIR/examples/text_to_image/train_text_to_image_lora_sdxl.py}"
ACCELERATE_BIN="${ACCELERATE_BIN:-accelerate}"

PRETRAINED_MODEL_NAME_OR_PATH="${PRETRAINED_MODEL_NAME_OR_PATH:-stabilityai/stable-diffusion-xl-base-1.0}"
PRETRAINED_VAE_MODEL_NAME_OR_PATH="${PRETRAINED_VAE_MODEL_NAME_OR_PATH:-madebyollin/sdxl-vae-fp16-fix}"
PRETRAINED_MODEL_VARIANT="${PRETRAINED_MODEL_VARIANT:-}"
DATASET_NAME="${DATASET_NAME:-}"
TRAIN_DATA_DIR="${TRAIN_DATA_DIR:-}"
IMAGE_COLUMN="${IMAGE_COLUMN:-image}"
CAPTION_COLUMN="${CAPTION_COLUMN:-text}"

MIXED_PRECISION="${MIXED_PRECISION:-fp16}"
RESOLUTION="${RESOLUTION:-1024}"
TRAIN_BATCH_SIZE="${TRAIN_BATCH_SIZE:-1}"
GRADIENT_ACCUMULATION_STEPS="${GRADIENT_ACCUMULATION_STEPS:-4}"
MAX_TRAIN_STEPS="${MAX_TRAIN_STEPS:-2000}"
LEARNING_RATE="${LEARNING_RATE:-1e-4}"
LR_SCHEDULER="${LR_SCHEDULER:-constant}"
LR_WARMUP_STEPS="${LR_WARMUP_STEPS:-0}"
RANK="${RANK:-16}"
CHECKPOINTING_STEPS="${CHECKPOINTING_STEPS:-250}"
CHECKPOINTS_TOTAL_LIMIT="${CHECKPOINTS_TOTAL_LIMIT:-4}"
MAX_GRAD_NORM="${MAX_GRAD_NORM:-1}"
SEED="${SEED:-42}"
NUM_WORKERS="${NUM_WORKERS:-4}"

GRADIENT_CHECKPOINTING="${GRADIENT_CHECKPOINTING:-true}"
ENABLE_XFORMERS="${ENABLE_XFORMERS:-false}"
CENTER_CROP="${CENTER_CROP:-true}"
RANDOM_FLIP="${RANDOM_FLIP:-false}"

VALIDATION_PROMPT="${VALIDATION_PROMPT:-}"
NUM_VALIDATION_IMAGES="${NUM_VALIDATION_IMAGES:-4}"
VALIDATION_EPOCHS="${VALIDATION_EPOCHS:-1}"

if [[ -z "$DATASET_NAME" && -z "$TRAIN_DATA_DIR" ]]; then
  echo "Error: set either DATASET_NAME or TRAIN_DATA_DIR before starting LoRA training." >&2
  exit 1
fi

if [[ -n "$DATASET_NAME" && -n "$TRAIN_DATA_DIR" ]]; then
  echo "Error: set only one of DATASET_NAME or TRAIN_DATA_DIR, not both." >&2
  exit 1
fi

if [[ -n "$TRAIN_DATA_DIR" && ! -d "$TRAIN_DATA_DIR" ]]; then
  echo "Error: TRAIN_DATA_DIR does not exist: $TRAIN_DATA_DIR" >&2
  exit 1
fi

if [[ ! -f "$TRAIN_SCRIPT" ]]; then
  echo "Error: training script not found: $TRAIN_SCRIPT" >&2
  echo "Clone diffusers first, for example: git clone https://github.com/huggingface/diffusers /root/diffusers" >&2
  exit 1
fi

if ! command -v "$ACCELERATE_BIN" >/dev/null 2>&1; then
  echo "Error: '$ACCELERATE_BIN' is not installed or not on PATH." >&2
  exit 1
fi

mkdir -p "$RUNS_DIR" "$LOG_DIR" "$OUTPUT_DIR"

if [[ -f "$PID_FILE" ]]; then
  existing_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "$existing_pid" ]] && kill -0 "$existing_pid" 2>/dev/null; then
    echo "Error: a LoRA run using PID file '$PID_FILE' is already active (pid=$existing_pid)." >&2
    exit 1
  fi
fi

"$ACCELERATE_BIN" config default >/dev/null 2>&1 || true

cmd=(
  "$ACCELERATE_BIN"
  launch
  --mixed_precision="$MIXED_PRECISION"
  "$TRAIN_SCRIPT"
  --pretrained_model_name_or_path="$PRETRAINED_MODEL_NAME_OR_PATH"
  --pretrained_vae_model_name_or_path="$PRETRAINED_VAE_MODEL_NAME_OR_PATH"
  --dataloader_num_workers="$NUM_WORKERS"
  --resolution="$RESOLUTION"
  --train_batch_size="$TRAIN_BATCH_SIZE"
  --gradient_accumulation_steps="$GRADIENT_ACCUMULATION_STEPS"
  --max_train_steps="$MAX_TRAIN_STEPS"
  --learning_rate="$LEARNING_RATE"
  --max_grad_norm="$MAX_GRAD_NORM"
  --lr_scheduler="$LR_SCHEDULER"
  --lr_warmup_steps="$LR_WARMUP_STEPS"
  --checkpointing_steps="$CHECKPOINTING_STEPS"
  --checkpoints_total_limit="$CHECKPOINTS_TOTAL_LIMIT"
  --rank="$RANK"
  --output_dir="$OUTPUT_DIR"
  --seed="$SEED"
)

if [[ -n "$PRETRAINED_MODEL_VARIANT" ]]; then
  cmd+=(--variant="$PRETRAINED_MODEL_VARIANT")
fi

if [[ -n "$DATASET_NAME" ]]; then
  cmd+=(--dataset_name="$DATASET_NAME")
else
  cmd+=(
    --train_data_dir="$TRAIN_DATA_DIR"
    --image_column="$IMAGE_COLUMN"
    --caption_column="$CAPTION_COLUMN"
  )
fi

if [[ "$GRADIENT_CHECKPOINTING" == "true" ]]; then
  cmd+=(--gradient_checkpointing)
fi

if [[ "$ENABLE_XFORMERS" == "true" ]]; then
  cmd+=(--enable_xformers_memory_efficient_attention)
fi

if [[ "$CENTER_CROP" == "true" ]]; then
  cmd+=(--center_crop)
fi

if [[ "$RANDOM_FLIP" == "true" ]]; then
  cmd+=(--random_flip)
fi

if [[ -n "$VALIDATION_PROMPT" ]]; then
  cmd+=(
    --validation_prompt="$VALIDATION_PROMPT"
    --num_validation_images="$NUM_VALIDATION_IMAGES"
    --validation_epochs="$VALIDATION_EPOCHS"
  )
fi

printf '%q ' "${cmd[@]}" > "$COMMAND_FILE"
printf '\n' >> "$COMMAND_FILE"
chmod 700 "$COMMAND_FILE"

(
  cd "$BACKEND_DIR"
  nohup "${cmd[@]}" >"$LOG_FILE" 2>&1 &
  echo $! > "$PID_FILE"
)

pid="$(cat "$PID_FILE")"

echo "Started SDXL LoRA training in background."
echo "  run name: $RUN_NAME"
echo "  pid:      $pid"
echo "  log:      $LOG_FILE"
echo "  output:   $OUTPUT_DIR"
echo "  command:  $COMMAND_FILE"
echo ""
echo "To monitor:"
echo "  bash PT3-backend/scripts/lora_bg_status.sh \"$PID_FILE\" \"$LOG_FILE\""
