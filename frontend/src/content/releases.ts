export interface ReleaseEntry {
  version: string
  date: string
  items: readonly string[]
}

export const releases: readonly ReleaseEntry[] = [
  {
    version: "v3.1.3",
    date: "2026-10-09",
    items: [
      "整合包 Musubi / AI Toolkit venv 失效基础 Python 时可自动修复",
      "Anima 训练支持 2B / 2.9B 规格选择与底模路径记忆",
      "Kohya 拆为独立引擎，可在设置中安装、修复与卸载",
      "支持配置默认训练引擎，以及记住上次使用的引擎",
    ],
  },
  {
    version: "v3.1.2",
    date: "2026-10-09",
    items: [
      "Kohya 拆为独立引擎，可在设置中安装、修复与卸载",
      "卸载仅清理 extensions/kohya，不触碰 GUI Python / Torch",
      "支持配置默认训练引擎，以及记住上次使用的引擎",
      "升级后首次 Kohya 训练前需先安装引擎",
    ],
  },
  {
    version: "v3.1.1",
    date: "2026-09-22",
    items: [
      "新增 DiffSynth 引擎，支持 Qwen-Image-2.1 BF16 文生图 LoRA",
      "支持 Comfy-Org 模型组件、图片与 TXT 标注及子目录重复次数",
      "支持 TE/VAE 缓存、CPU 卸载、分桶及训练中预览",
      "完成 RTX 4090 短训与独立 ComfyUI LoRA 回载出图验证",
    ],
  },
  {
    version: "v3.1.0",
    date: "2026-09-18",
    items: [
      "Anima Fast v1.17.1：Anima 2.9B、T-LoRA 与训练安全门禁",
      "统一训练引擎注册表，并新增 AI Toolkit / Klein 支持",
      "插件市场、插件宿主与 Pi Agent 扩展能力",
      "任务工作台、多 GPU、LyCORIS 与断点恢复稳定性修复",
    ],
  },
  {
    version: "v3.0.0",
    date: "2026-08-16",
    items: [
      "Vue3 四栏工作台正式版（训练 / 数据集 / 任务 / 设置）",
      "Krea 2（Musubi）与 Kohya / Anima Fast 引擎管理",
      "任务页 Loss/预览可收起；侧栏任务角标",
      "网页路径浏览（Linux/远程）；下载源偏好",
    ],
  },
  { version: "v2.9.2-beta.2", date: "2026-08-07", items: ["修复启动时打开空白训练监控页（6008 连接被拒绝）", "仅在监控就绪后打开浏览器标签；可用 /train-monitor"] },
  { version: "v2.9.2-beta.1", date: "2026-08-07", items: ["Vue3 四栏 IA 内测线（训练 / 数据集 / 任务 / 设置）", "品牌统一为 Next Trainer（内测版本号走 2.9.x）", "训练引擎管理与 Fast 就绪态", "开源致谢页与 lite/full 双整合包", "钉死 protobuf==3.20.3（Flux/SD3）"] },
  { version: "v2.9.0", date: "2026-07-22", items: ["Anima Fast 高分辨率 bucket 参数与训练前检查", "Anima 标准模式 LoKr 无效参数清理", "本地 WD 打标模型加载与 CUDA/CPU 回退改进", "Windows 整合包数据目录和 junction 修复"] },
  { version: "v2.8.35", date: "2026-06-28", items: ["修复 Windows 更新脚本路径、换行与 PowerShell 5.1 编码兼容", "新增 Fix-Portable-Bats.bat"] },
  { version: "v2.8.3", date: "2026-06-28", items: ["新增配置导出规范化 API", "改善整合包 Hugging Face、ModelScope 与文件选择器路径"] },
  { version: "v2.8.2", date: "2026-06-27", items: ["修复 SDXL 训练路由与离线 tokenizer", "默认 WD 打标模型开箱即用", "修复预览图和训练配置导入"] },
]
