import type { TrainingSectionSpec } from "./trainingRenderer";

export interface AnimaRoutePlan {
  path: string;
  heading: string;
  modelTrainType: "anima-lora" | "anima-finetune";
  schemaFile: string;
  backendEntrypoint: string;
  summary: string;
  nextWork: string[];
}
export interface AnimaForm {
  [key: string]: unknown;
  pretrained_model_name_or_path: string;
  vae: string;
  qwen3: string;
  t5_tokenizer_path: string;
  llm_adapter_path: string;
  resume: string;
  train_data_dir: string;
  output_dir: string;
  output_name: string;
  lora_type: "lora" | "lokr" | "tlora" | "lora_fa" | "vera" | "loha";
  max_train_epochs: number;
  train_batch_size: number;
  gradient_accumulation_steps: number;
  qwen3_max_token_length: number;
  t5_max_token_length: number;
  learning_rate: string;
  self_attn_lr: string;
  cross_attn_lr: string;
  mlp_lr: string;
  mod_lr: string;
  llm_adapter_lr: string;
  unet_lr: string;
  lr_scheduler: "linear" | "cosine" | "cosine_with_restarts" | "polynomial" | "constant" | "constant_with_warmup";
  lr_warmup_steps: number;
  lr_scheduler_num_cycles: number;
  optimizer_args_custom: string[];
  min_snr_gamma: string;
  prodigy_d0: string;
  prodigy_d_coef: string;
  network_dim: number;
  network_alpha: number;
  network_args_custom: string[];
  resolution: string;
  enable_bucket: boolean;
  min_bucket_reso: number;
  max_bucket_reso: number;
  bucket_reso_steps: number;
  mixed_precision: "bf16" | "fp16" | "no";
  optimizer_type: string;
  attn_mode: "" | "torch" | "xformers" | "sageattn" | "flash";
  timestep_sampling: "sigma" | "uniform" | "sigmoid" | "shift" | "flux_shift";
  sigmoid_scale: number;
  discrete_flow_shift: number;
  weighting_scheme: "sigma_sqrt" | "logit_normal" | "mode" | "cosmap" | "none" | "uniform";
  logit_mean: string;
  logit_std: string;
  mode_scale: string;
  split_attn: boolean;
  vae_chunk_size: string;
  vae_disable_cache: boolean;
  unsloth_offload_checkpointing: boolean;
  gradient_checkpointing: boolean;
  network_train_unet_only: boolean;
  network_train_text_encoder_only: boolean;
  cache_latents: boolean;
  cache_latents_to_disk: boolean;
  cache_text_encoder_outputs: boolean;
  cache_text_encoder_outputs_to_disk: boolean;
  fp8_base: boolean;
  fp8_base_unet: boolean;
  persistent_data_loader_workers: boolean;
  max_data_loader_n_workers: number;
  text_encoder_batch_size: string;
  disable_mmap_load_safetensors: boolean;
  blocks_to_swap: string;
  cpu_offload_checkpointing: boolean;
  enable_preview: boolean;
  positive_prompts: string;
  negative_prompts: string;
  sample_width: number;
  sample_height: number;
  sample_cfg: number;
  sample_seed: number;
  sample_steps: number;
  sample_sampler: "euler" | "k_euler";
  sample_scheduler: "simple";
  sample_at_first: boolean;
  sample_every_n_epochs: number;
  sample_prompts: string;
  caption_extension: string;
  prefer_json_caption: boolean;
  enable_debug_options: boolean;
  anima_profile_window: number;
  anima_nan_check_interval: number;
  anima_debug_mode: boolean;
  anima_rope_mismatch_mode: "strict" | "resample";
  anima_rope_max_seq_tokens: number;
  noise_offset: string;
  multires_noise_iterations: string;
  multires_noise_discount: string;
  color_aug: boolean;
  flip_aug: boolean;
  random_crop: boolean;
  seed: number;
  clip_skip: number;
  ui_custom_params: string;
  ddp_timeout: string;
  ddp_gradient_as_bucket_view: boolean;
}

export const ANIMA_STORAGE_KEY = "sd-trainer-source-anima-configs";

export const ANIMA_ROUTES: Record<string, AnimaRoutePlan> = {
  "/lora/sd3.html": {
    path: "/lora/sd3.html",
    heading: "Anima Stable Diffusion LoRA",
    modelTrainType: "anima-lora",
    schemaFile: "mikazuki/schema/sd3-lora.ts",
    backendEntrypoint: "scripts/dev/anima_train_network.py",
    summary: "Preserves the historical sd3 URL while routing to the Anima LoRA backend.",
    nextWork: [
      "Move Anima LoRA form sections from schema-driven runtime into source-owned components.",
      "Keep the sd3-lora route key stable for saved configs and old links.",
      "Add browser smoke before replacing the production dist route.",
    ],
  },
  "/lora/anima-finetune.html": {
    path: "/lora/anima-finetune.html",
    heading: "Anima Finetune",
    modelTrainType: "anima-finetune",
    schemaFile: "mikazuki/schema/anima-finetune.ts",
    backendEntrypoint: "scripts/dev/anima_train.py",
    summary: "Tracks full DiT finetune work without touching SD or Flux training pages.",
    nextWork: [
      "Source-own the high-risk Anima full finetune options first.",
      "Keep full finetune defaults aligned with backend adapter tests.",
      "Add save/load config compatibility checks before production replacement.",
    ],
  },
};

export const animaDefaults: AnimaForm = {
  pretrained_model_name_or_path: "./sd-models/anima/anima-base-v1.0.safetensors",
  vae: "./sd-models/anima/qwen_image_vae.safetensors",
  qwen3: "./sd-models/anima/qwen_3_06b_base.safetensors",
  t5_tokenizer_path: "",
  llm_adapter_path: "",
  resume: "",
  train_data_dir: "",
  output_dir: "output",
  output_name: "anima",
  lora_type: "lora",
  max_train_epochs: 10,
  train_batch_size: 1,
  gradient_accumulation_steps: 1,
  qwen3_max_token_length: 512,
  t5_max_token_length: 512,
  learning_rate: "1e-5",
  self_attn_lr: "",
  cross_attn_lr: "",
  mlp_lr: "",
  mod_lr: "",
  llm_adapter_lr: "",
  unet_lr: "1e-4",
  lr_scheduler: "cosine_with_restarts",
  lr_warmup_steps: 0,
  lr_scheduler_num_cycles: 1,
  optimizer_args_custom: [],
  min_snr_gamma: "",
  prodigy_d0: "",
  prodigy_d_coef: "2.0",
  network_dim: 32,
  network_alpha: 16,
  network_args_custom: [],
  resolution: "1024,1024",
  enable_bucket: true,
  min_bucket_reso: 256,
  max_bucket_reso: 2048,
  bucket_reso_steps: 64,
  mixed_precision: "bf16",
  optimizer_type: "AdamW8bit",
  attn_mode: "",
  timestep_sampling: "shift",
  sigmoid_scale: 1,
  discrete_flow_shift: 3,
  weighting_scheme: "uniform",
  logit_mean: "",
  logit_std: "",
  mode_scale: "",
  split_attn: false,
  vae_chunk_size: "",
  vae_disable_cache: false,
  unsloth_offload_checkpointing: false,
  gradient_checkpointing: true,
  network_train_unet_only: true,
  network_train_text_encoder_only: false,
  cache_latents: true,
  cache_latents_to_disk: true,
  cache_text_encoder_outputs: true,
  cache_text_encoder_outputs_to_disk: true,
  fp8_base: false,
  fp8_base_unet: false,
  persistent_data_loader_workers: false,
  max_data_loader_n_workers: 0,
  text_encoder_batch_size: "",
  disable_mmap_load_safetensors: false,
  blocks_to_swap: "",
  cpu_offload_checkpointing: false,
  enable_preview: true,
  positive_prompts:
    "1girl, solo, smile, japanese clothes, kimono, blue eyes, closed mouth, upper body, looking at viewer",
  negative_prompts:
    "nsfw, explicit, sexual content, worst quality, low quality, artist name, jpeg artifacts",
  sample_width: 1024,
  sample_height: 1024,
  sample_cfg: 4.5,
  sample_seed: 42,
  sample_steps: 40,
  sample_sampler: "euler",
  sample_scheduler: "simple",
  sample_at_first: true,
  sample_every_n_epochs: 2,
  sample_prompts: "",
  caption_extension: ".txt",
  prefer_json_caption: true,
  enable_debug_options: false,
  anima_profile_window: 0,
  anima_nan_check_interval: 0,
  anima_debug_mode: false,
  anima_rope_mismatch_mode: "strict",
  anima_rope_max_seq_tokens: 0,
  noise_offset: "",
  multires_noise_iterations: "",
  multires_noise_discount: "",
  color_aug: false,
  flip_aug: false,
  random_crop: false,
  seed: 1337,
  clip_skip: 2,
  ui_custom_params: "",
  ddp_timeout: "",
  ddp_gradient_as_bucket_view: false,
};

export const animaModelAssetSection: TrainingSectionSpec<AnimaForm> = {
  title: "Model Assets",
  fields: [
    {
      kind: "text",
      key: "pretrained_model_name_or_path",
      id: "anima-pretrained-model",
      label: "pretrained_model_name_or_path",
      placeholder: "D:/models/anima-base-v1.0.safetensors",
      description: "Anima DiT / transformer checkpoint path.",
      role: "file",
    },
    {
      kind: "text",
      key: "vae",
      id: "anima-vae",
      label: "vae",
      placeholder: "D:/models/qwen_image_vae.safetensors",
      description: "Qwen Image VAE path.",
      role: "file",
    },
    {
      kind: "text",
      key: "qwen3",
      id: "anima-qwen3",
      label: "qwen3",
      placeholder: "D:/models/qwen_3_06b_base.safetensors",
      description: "Qwen3 text model path.",
      role: "file",
    },
    {
      kind: "text",
      key: "t5_tokenizer_path",
      id: "anima-t5-tokenizer-path",
      label: "t5_tokenizer_path",
      description: "Optional T5 tokenizer folder. Empty uses the bundled config.",
      role: "folder",
    },
    {
      kind: "text",
      key: "llm_adapter_path",
      id: "anima-llm-adapter-path",
      label: "llm_adapter_path",
      role: "file",
    },
    {
      kind: "text",
      key: "resume",
      id: "anima-resume",
      label: "resume",
      role: "folder",
    },
  ],
};

export const animaDatasetOutputSection: TrainingSectionSpec<AnimaForm> = {
  title: "Dataset And Output",
  fields: [
    {
      kind: "text",
      key: "train_data_dir",
      id: "anima-train-data-dir",
      label: "train_data_dir",
      placeholder: "D:/datasets/anima",
      role: "folder",
    },
    {
      kind: "text",
      key: "output_dir",
      id: "anima-output-dir",
      label: "output_dir",
      role: "folder",
    },
    {
      kind: "text",
      key: "output_name",
      id: "anima-output-name",
      label: "output_name",
    },
    {
      kind: "row",
      fields: [
        {
          kind: "text",
          key: "resolution",
          id: "anima-resolution",
          label: "resolution",
        },
        {
          kind: "text",
          key: "caption_extension",
          id: "anima-caption-extension",
          label: "caption_extension",
        },
        {
          kind: "checkbox",
          key: "prefer_json_caption",
          id: "anima-prefer-json-caption",
          label: "prefer_json_caption",
        },
      ],
    },
    {
      kind: "row",
      fields: [
        { kind: "text", key: "self_attn_lr", id: "anima-self-attn-lr", label: "self_attn_lr" },
        { kind: "text", key: "cross_attn_lr", id: "anima-cross-attn-lr", label: "cross_attn_lr" },
        { kind: "text", key: "mlp_lr", id: "anima-mlp-lr", label: "mlp_lr" },
      ],
    },
    {
      kind: "row",
      fields: [
        { kind: "text", key: "mod_lr", id: "anima-mod-lr", label: "mod_lr" },
        { kind: "text", key: "llm_adapter_lr", id: "anima-llm-adapter-lr", label: "llm_adapter_lr" },
        { kind: "text", key: "min_snr_gamma", id: "anima-min-snr-gamma", label: "min_snr_gamma" },
      ],
    },
    {
      kind: "row",
      fields: [
        {
          kind: "checkbox",
          key: "enable_bucket",
          id: "anima-enable-bucket",
          label: "enable_bucket",
        },
        {
          kind: "number",
          key: "min_bucket_reso",
          id: "anima-min-bucket-reso",
          label: "min_bucket_reso",
          min: 64,
        },
        {
          kind: "number",
          key: "max_bucket_reso",
          id: "anima-max-bucket-reso",
          label: "max_bucket_reso",
          min: 64,
        },
      ],
    },
    {
      kind: "number",
      key: "bucket_reso_steps",
      id: "anima-bucket-reso-steps",
      label: "bucket_reso_steps",
      min: 1,
    },
  ],
};

export const animaTrainingSection: TrainingSectionSpec<AnimaForm> = {
  title: "Training",
  fields: [
    {
      kind: "row",
      fields: [
        { kind: "number", key: "max_train_epochs", id: "anima-epochs", label: "max_train_epochs", min: 1 },
        { kind: "number", key: "train_batch_size", id: "anima-train-batch-size", label: "train_batch_size", min: 1 },
        {
          kind: "number",
          key: "gradient_accumulation_steps",
          id: "anima-gradient-accumulation-steps",
          label: "gradient_accumulation_steps",
          min: 1,
        },
      ],
    },
    {
      kind: "row",
      fields: [
        { kind: "text", key: "learning_rate", id: "anima-learning-rate", label: "learning_rate" },
        { kind: "text", key: "optimizer_type", id: "anima-optimizer", label: "optimizer_type" },
        {
          kind: "select",
          key: "mixed_precision",
          id: "anima-mixed-precision",
          label: "mixed_precision",
          options: ["bf16", "fp16", "no"],
        },
      ],
    },
    {
      kind: "row",
      fields: [
        {
          kind: "select",
          key: "lr_scheduler",
          id: "anima-lr-scheduler",
          label: "lr_scheduler",
          options: ["linear", "cosine", "cosine_with_restarts", "polynomial", "constant", "constant_with_warmup"],
        },
        { kind: "number", key: "lr_warmup_steps", id: "anima-lr-warmup-steps", label: "lr_warmup_steps", min: 0 },
        {
          kind: "number",
          key: "qwen3_max_token_length",
          id: "anima-qwen3-max-token-length",
          label: "qwen3_max_token_length",
          min: 1,
        },
      ],
    },
    {
      kind: "number",
      key: "lr_scheduler_num_cycles",
      id: "anima-lr-scheduler-num-cycles",
      label: "lr_scheduler_num_cycles",
      min: 1,
      visibleWhen: { key: "lr_scheduler", equals: "cosine_with_restarts" },
    },
    {
      kind: "row",
      visibleWhen: { key: "optimizer_type", equals: "Prodigy" },
      fields: [
        { kind: "text", key: "prodigy_d0", id: "anima-prodigy-d0", label: "prodigy_d0" },
        { kind: "text", key: "prodigy_d_coef", id: "anima-prodigy-d-coef", label: "prodigy_d_coef" },
      ],
    },
    {
      kind: "table",
      key: "optimizer_args_custom",
      id: "anima-optimizer-args-custom",
      label: "optimizer_args_custom",
      description: "Custom optimizer_args entries, one argument per row.",
    },
    { kind: "number", key: "t5_max_token_length", id: "anima-t5-max-token-length", label: "t5_max_token_length", min: 1 },
    {
      kind: "checkbox",
      key: "gradient_checkpointing",
      id: "anima-gradient-checkpointing",
      label: "gradient_checkpointing",
    },
  ],
};

export const animaLoraAdapterSection: TrainingSectionSpec<AnimaForm> = {
  title: "LoRA Adapter",
  fields: [
    {
      kind: "row",
      fields: [
        {
          kind: "select",
          key: "lora_type",
          id: "anima-lora-type",
          label: "lora_type",
          options: ["lora", "lokr", "tlora", "lora_fa", "vera", "loha"],
        },
        { kind: "text", key: "unet_lr", id: "anima-unet-lr", label: "unet_lr" },
        { kind: "number", key: "network_dim", id: "anima-network-dim", label: "network_dim", min: 1 },
      ],
    },
    { kind: "number", key: "network_alpha", id: "anima-network-alpha", label: "network_alpha", min: 1 },
    {
      kind: "table",
      key: "network_args_custom",
      id: "anima-network-args-custom",
      label: "network_args_custom",
      description: "Custom network_args entries, one argument per row.",
    },
    {
      kind: "row",
      fields: [
        {
          kind: "checkbox",
          key: "network_train_unet_only",
          id: "anima-network-train-unet-only",
          label: "network_train_unet_only",
        },
        {
          kind: "checkbox",
          key: "network_train_text_encoder_only",
          id: "anima-network-train-text-encoder-only",
          label: "network_train_text_encoder_only",
        },
      ],
    },
  ],
};

export const animaParametersSection: TrainingSectionSpec<AnimaForm> = {
  title: "Anima Parameters",
  fields: [
    {
      kind: "row",
      fields: [
        {
          kind: "select",
          key: "attn_mode",
          id: "anima-attn-mode",
          label: "attn_mode",
          options: ["", "torch", "xformers", "sageattn", "flash"],
        },
        {
          kind: "select",
          key: "timestep_sampling",
          id: "anima-timestep-sampling",
          label: "timestep_sampling",
          options: ["sigma", "uniform", "sigmoid", "shift", "flux_shift"],
        },
        { kind: "number", key: "sigmoid_scale", id: "anima-sigmoid-scale", label: "sigmoid_scale", min: 0, step: 0.001 },
      ],
    },
    {
      kind: "row",
      fields: [
        {
          kind: "number",
          key: "discrete_flow_shift",
          id: "anima-discrete-flow-shift",
          label: "discrete_flow_shift",
          min: 0,
          step: 0.001,
        },
        {
          kind: "select",
          key: "weighting_scheme",
          id: "anima-weighting-scheme",
          label: "weighting_scheme",
          options: ["sigma_sqrt", "logit_normal", "mode", "cosmap", "none", "uniform"],
        },
      ],
    },
    {
      kind: "row",
      fields: [
        {
          kind: "text",
          key: "logit_mean",
          id: "anima-logit-mean",
          label: "logit_mean",
          description: "Optional logit_normal mean.",
          visibleWhen: { key: "weighting_scheme", equals: "logit_normal" },
        },
        {
          kind: "text",
          key: "logit_std",
          id: "anima-logit-std",
          label: "logit_std",
          description: "Optional logit_normal stddev.",
          visibleWhen: { key: "weighting_scheme", equals: "logit_normal" },
        },
        {
          kind: "text",
          key: "mode_scale",
          id: "anima-mode-scale",
          label: "mode_scale",
          description: "Optional mode weighting scale.",
          visibleWhen: { key: "weighting_scheme", equals: "mode" },
        },
      ],
    },
    {
      kind: "row",
      fields: [
        { kind: "checkbox", key: "split_attn", id: "anima-split-attn", label: "split_attn" },
        { kind: "text", key: "vae_chunk_size", id: "anima-vae-chunk-size", label: "vae_chunk_size", description: "Even VAE chunk size." },
        { kind: "checkbox", key: "vae_disable_cache", id: "anima-vae-disable-cache", label: "vae_disable_cache" },
      ],
    },
    {
      kind: "checkbox",
      key: "unsloth_offload_checkpointing",
      id: "anima-unsloth-offload-checkpointing",
      label: "unsloth_offload_checkpointing",
      description: "CPU RAM activation offload. Keep off with blocks_to_swap / cpu_offload_checkpointing.",
    },
  ],
};

export const animaCacheSection: TrainingSectionSpec<AnimaForm> = {
  title: "Cache",
  fields: [
    {
      kind: "row",
      fields: [
        { kind: "checkbox", key: "cache_latents", id: "anima-cache-latents", label: "cache_latents" },
        { kind: "checkbox", key: "cache_latents_to_disk", id: "anima-cache-latents-to-disk", label: "cache_latents_to_disk" },
        {
          kind: "checkbox",
          key: "cache_text_encoder_outputs",
          id: "anima-cache-text-encoder-outputs",
          label: "cache_text_encoder_outputs",
        },
      ],
    },
    {
      kind: "row",
      fields: [
        {
          kind: "checkbox",
          key: "cache_text_encoder_outputs_to_disk",
          id: "anima-cache-text-encoder-outputs-to-disk",
          label: "cache_text_encoder_outputs_to_disk",
        },
        { kind: "checkbox", key: "fp8_base", id: "anima-fp8-base", label: "fp8_base" },
        { kind: "checkbox", key: "fp8_base_unet", id: "anima-fp8-base-unet", label: "fp8_base_unet" },
      ],
    },
    {
      kind: "row",
      fields: [
        {
          kind: "checkbox",
          key: "persistent_data_loader_workers",
          id: "anima-persistent-data-loader-workers",
          label: "persistent_data_loader_workers",
        },
        {
          kind: "number",
          key: "max_data_loader_n_workers",
          id: "anima-max-data-loader-n-workers",
          label: "max_data_loader_n_workers",
          min: 0,
        },
        {
          kind: "text",
          key: "text_encoder_batch_size",
          id: "anima-text-encoder-batch-size",
          label: "text_encoder_batch_size",
          description: "Optional text encoder cache batch size.",
        },
      ],
    },
    {
      kind: "row",
      fields: [
        {
          kind: "checkbox",
          key: "disable_mmap_load_safetensors",
          id: "anima-disable-mmap-load-safetensors",
          label: "disable_mmap_load_safetensors",
        },
        { kind: "text", key: "blocks_to_swap", id: "anima-blocks-to-swap", label: "blocks_to_swap" },
        {
          kind: "checkbox",
          key: "cpu_offload_checkpointing",
          id: "anima-cpu-offload-checkpointing",
          label: "cpu_offload_checkpointing",
        },
      ],
    },
  ],
};

export const animaPreviewSection: TrainingSectionSpec<AnimaForm> = {
  title: "Preview",
  fields: [
    { kind: "checkbox", key: "enable_preview", id: "anima-enable-preview", label: "enable_preview" },
    {
      kind: "textarea",
      key: "positive_prompts",
      id: "anima-positive-prompts",
      label: "positive_prompts",
      rows: 4,
      visibleWhen: { key: "enable_preview", equals: true },
    },
    {
      kind: "textarea",
      key: "negative_prompts",
      id: "anima-negative-prompts",
      label: "negative_prompts",
      rows: 4,
      visibleWhen: { key: "enable_preview", equals: true },
    },
    {
      kind: "textarea",
      key: "sample_prompts",
      id: "anima-sample-prompts",
      label: "sample_prompts",
      rows: 4,
      visibleWhen: { key: "enable_preview", equals: true },
    },
    {
      kind: "row",
      visibleWhen: { key: "enable_preview", equals: true },
      fields: [
        { kind: "number", key: "sample_width", id: "anima-sample-width", label: "sample_width", min: 64 },
        { kind: "number", key: "sample_height", id: "anima-sample-height", label: "sample_height", min: 64 },
        {
          kind: "number",
          key: "sample_every_n_epochs",
          id: "anima-sample-every-n-epochs",
          label: "sample_every_n_epochs",
          min: 1,
        },
      ],
    },
    {
      kind: "row",
      visibleWhen: { key: "enable_preview", equals: true },
      fields: [
        { kind: "number", key: "sample_cfg", id: "anima-sample-cfg", label: "sample_cfg", min: 1, step: 0.1 },
        { kind: "number", key: "sample_seed", id: "anima-sample-seed", label: "sample_seed", min: 0 },
        { kind: "number", key: "sample_steps", id: "anima-sample-steps", label: "sample_steps", min: 1 },
      ],
    },
    {
      kind: "row",
      visibleWhen: { key: "enable_preview", equals: true },
      fields: [
        {
          kind: "select",
          key: "sample_sampler",
          id: "anima-sample-sampler",
          label: "sample_sampler",
          options: ["euler", "k_euler"],
        },
        {
          kind: "select",
          key: "sample_scheduler",
          id: "anima-sample-scheduler",
          label: "sample_scheduler",
          options: ["simple"],
        },
        { kind: "checkbox", key: "sample_at_first", id: "anima-sample-at-first", label: "sample_at_first" },
      ],
    },
  ],
};

export const animaDebugSection: TrainingSectionSpec<AnimaForm> = {
  title: "Debug Options",
  fields: [
    {
      kind: "checkbox",
      key: "enable_debug_options",
      id: "anima-enable-debug-options",
      label: "enable_debug_options",
      description: "Show Anima debug options. Normal training usually keeps this off.",
    },
    {
      kind: "row",
      visibleWhen: { key: "enable_debug_options", equals: true },
      fields: [
        {
          kind: "number",
          key: "anima_profile_window",
          id: "anima-profile-window",
          label: "anima_profile_window",
          min: 0,
        },
        {
          kind: "number",
          key: "anima_nan_check_interval",
          id: "anima-nan-check-interval",
          label: "anima_nan_check_interval",
          min: 0,
        },
        {
          kind: "checkbox",
          key: "anima_debug_mode",
          id: "anima-debug-mode",
          label: "anima_debug_mode",
        },
      ],
    },
    {
      kind: "row",
      visibleWhen: { key: "enable_debug_options", equals: true },
      fields: [
        {
          kind: "select",
          key: "anima_rope_mismatch_mode",
          id: "anima-rope-mismatch-mode",
          label: "anima_rope_mismatch_mode",
          options: ["strict", "resample"],
        },
        {
          kind: "number",
          key: "anima_rope_max_seq_tokens",
          id: "anima-rope-max-seq-tokens",
          label: "anima_rope_max_seq_tokens",
          min: 0,
        },
      ],
    },
  ],
};

export const animaNoiseSection: TrainingSectionSpec<AnimaForm> = {
  title: "Noise Settings",
  fields: [
    {
      kind: "row",
      fields: [
        { kind: "text", key: "noise_offset", id: "anima-noise-offset", label: "noise_offset" },
        {
          kind: "text",
          key: "multires_noise_iterations",
          id: "anima-multires-noise-iterations",
          label: "multires_noise_iterations",
        },
        {
          kind: "text",
          key: "multires_noise_discount",
          id: "anima-multires-noise-discount",
          label: "multires_noise_discount",
        },
      ],
    },
  ],
};

export const animaDataEnhancementSection: TrainingSectionSpec<AnimaForm> = {
  title: "Data Enhancement",
  fields: [
    {
      kind: "row",
      fields: [
        { kind: "checkbox", key: "color_aug", id: "anima-color-aug", label: "color_aug" },
        { kind: "checkbox", key: "flip_aug", id: "anima-flip-aug", label: "flip_aug" },
        { kind: "checkbox", key: "random_crop", id: "anima-random-crop", label: "random_crop" },
      ],
    },
  ],
};

export const animaOtherSection: TrainingSectionSpec<AnimaForm> = {
  title: "Other",
  fields: [
    {
      kind: "row",
      fields: [
        { kind: "number", key: "seed", id: "anima-seed", label: "seed", min: 0 },
        {
          kind: "number",
          key: "clip_skip",
          id: "anima-clip-skip",
          label: "clip_skip",
          min: 0,
          step: 1,
          role: "slider",
        },
      ],
    },
    {
      kind: "textarea",
      key: "ui_custom_params",
      id: "anima-ui-custom-params",
      label: "ui_custom_params",
      rows: 5,
      description: "Advanced TOML override text. Use carefully.",
    },
  ],
};

export const animaDistributedSection: TrainingSectionSpec<AnimaForm> = {
  title: "Distributed Training",
  fields: [
    {
      kind: "row",
      fields: [
        { kind: "text", key: "ddp_timeout", id: "anima-ddp-timeout", label: "ddp_timeout" },
        {
          kind: "checkbox",
          key: "ddp_gradient_as_bucket_view",
          id: "anima-ddp-gradient-as-bucket-view",
          label: "ddp_gradient_as_bucket_view",
        },
      ],
    },
  ],
};

export function animaSectionsForPlan(plan: AnimaRoutePlan): TrainingSectionSpec<AnimaForm>[] {
  return [
    animaModelAssetSection,
    animaDatasetOutputSection,
    animaTrainingSection,
    ...(plan.modelTrainType === "anima-lora" ? [animaLoraAdapterSection] : []),
    animaParametersSection,
    animaCacheSection,
    animaPreviewSection,
    animaDebugSection,
    animaNoiseSection,
    animaDataEnhancementSection,
    animaOtherSection,
    animaDistributedSection,
  ];
}




