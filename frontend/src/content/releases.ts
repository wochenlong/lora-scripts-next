export interface ReleaseEntry {
  version: string
  date: string
  items: readonly string[]
}

export const releases: readonly ReleaseEntry[] = [
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
