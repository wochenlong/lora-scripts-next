import { createRouter, createWebHistory, type RouteRecordRaw } from "vue-router"
const HomePage = () => import("./pages/HomePage.vue")
const IntegrationPage = () => import("./pages/IntegrationPage.vue")
const NotFoundPage = () => import("./pages/NotFoundPage.vue")
const TasksPage = () => import("./pages/TasksPage.vue")
const ToolsPage = () => import("./pages/ToolsPage.vue")
const DatasetPage = () => import("./pages/DatasetPage.vue")
const TrainingWorkbenchPage = () => import("./pages/TrainingWorkbenchPage.vue")
const SettingsContainerPage = () => import("./pages/SettingsContainerPage.vue")
const GuidePage = () => import("./pages/GuidePage.vue")
const ParamsPage = () => import("./pages/ParamsPage.vue")

const trainingQuery = (model: string, engine: string, target: string) => ({
  path: "/training",
  query: { model, engine, target },
})

const routes: RouteRecordRaw[] = [
  { path: "/", component: HomePage, meta: { title: "LoRA Scripts Next" } },
  { path: "/training", component: TrainingWorkbenchPage, meta: { title: "训练" } },
  { path: "/dataset", redirect: "/dataset/editor" },
  { path: "/dataset/editor", component: DatasetPage, props: { tab: "editor" }, meta: { title: "数据集" } },
  { path: "/dataset/tagger", component: DatasetPage, props: { tab: "tagger" }, meta: { title: "数据集" } },
  { path: "/tasks", component: TasksPage, meta: { title: "任务" } },
  { path: "/settings", redirect: "/settings/ui" },
  { path: "/settings/ui", component: SettingsContainerPage, props: { tab: "ui" }, meta: { title: "设置" } },
  { path: "/settings/about", component: SettingsContainerPage, props: { tab: "about" }, meta: { title: "设置" } },
  { path: "/settings/changelog", component: SettingsContainerPage, props: { tab: "changelog" }, meta: { title: "设置" } },
  { path: "/help/guide.html", component: GuidePage, meta: { title: "新手上路" } },
  // 旧 URL → 新 IA redirect
  { path: "/lora/index.html", redirect: "/training" },
  { path: "/lora/basic.html", redirect: () => trainingQuery("sd", "kohya", "lora") },
  { path: "/lora/master.html", redirect: () => trainingQuery("sd", "kohya", "lora") },
  { path: "/lora/sdxl.html", redirect: () => trainingQuery("sd", "kohya", "lora") },
  { path: "/lora/flux.html", redirect: () => trainingQuery("flux", "kohya", "lora") },
  { path: "/lora/sd3.html", redirect: () => trainingQuery("anima", "kohya", "lora") },
  { path: "/lora/anima-fast.html", redirect: () => trainingQuery("anima", "anima-fast", "lora") },
  { path: "/lora/anima-fast", redirect: () => trainingQuery("anima", "anima-fast", "lora") },
  { path: "/lora/anima-finetune.html", redirect: () => trainingQuery("anima", "kohya", "finetune") },
  { path: "/dreambooth/index.html", redirect: () => trainingQuery("sd", "kohya", "finetune") },
  { path: "/tagger.html", redirect: "/dataset/tagger" },
  { path: "/native-tageditor.html", redirect: "/dataset/editor" },
  { path: "/dataset-editor.html", redirect: "/dataset/editor" },
  { path: "/task.html", redirect: "/tasks" },
  { path: "/other/settings.html", redirect: "/settings/ui" },
  { path: "/other/about.html", redirect: "/settings/about" },
  { path: "/other/changelog.html", redirect: "/settings/changelog" },
  // 未纳入 v1 导航但保留可访问的页面
  {
    path: "/tensorboard.html",
    component: IntegrationPage,
    props: { title: "TensorBoard", src: "/proxy/tensorboard/", configurable: true },
    meta: { title: "TensorBoard" },
  },
  { path: "/lora/tools.html", component: ToolsPage, meta: { title: "LoRA 脚本工具" } },
  { path: "/lora/params.html", component: ParamsPage, meta: { title: "训练参数调节" } },
  {
    path: "/tageditor.html",
    component: IntegrationPage,
    props: { title: "旧版标签编辑器", src: "/proxy/tageditor/" },
    meta: { title: "旧版标签编辑器" },
  },
  { path: "/:pathMatch(.*)*", component: NotFoundPage, meta: { title: "页面不存在" } },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

router.afterEach((route) => {
  const title = typeof route.meta.title === "string" ? route.meta.title : "LoRA Scripts Next"
  document.title = `${title} | LoRA Scripts Next`
})

export default router
