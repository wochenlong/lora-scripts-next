import { createRouter, createWebHistory, type RouteRecordRaw } from "vue-router"
import { i18n } from "./i18n"
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
  { path: "/", component: HomePage, meta: { titleKey: "app.brand" } },
  { path: "/training", component: TrainingWorkbenchPage, meta: { titleKey: "training.title" } },
  { path: "/dataset", redirect: "/dataset/tagger" },
  { path: "/dataset/editor", component: DatasetPage, props: { tab: "editor" }, meta: { titleKey: "dataset.title" } },
  { path: "/dataset/tagger", component: DatasetPage, props: { tab: "tagger" }, meta: { titleKey: "dataset.title" } },
  { path: "/tasks", component: TasksPage, meta: { titleKey: "tasks.title" } },
  { path: "/settings", redirect: "/settings/ui" },
  { path: "/settings/ui", component: SettingsContainerPage, props: { tab: "ui" }, meta: { titleKey: "settings.title" } },
  { path: "/settings/about", component: SettingsContainerPage, props: { tab: "about" }, meta: { titleKey: "settings.title" } },
  { path: "/settings/changelog", component: SettingsContainerPage, props: { tab: "changelog" }, meta: { titleKey: "settings.title" } },
  { path: "/help/guide.html", component: GuidePage, meta: { titleKey: "guide.title" } },
  // 旧 URL → 新 IA redirect
  { path: "/lora/index.html", redirect: "/training" },
  { path: "/lora/basic.html", redirect: () => trainingQuery("sd15", "kohya", "lora") },
  { path: "/lora/master.html", redirect: () => trainingQuery("sdxl", "kohya", "lora") },
  { path: "/lora/sdxl.html", redirect: () => trainingQuery("sdxl", "kohya", "lora") },
  { path: "/lora/flux.html", redirect: () => trainingQuery("flux", "kohya", "lora") },
  { path: "/lora/sd3.html", redirect: () => trainingQuery("anima", "kohya", "lora") },
  { path: "/lora/anima-fast.html", redirect: () => trainingQuery("anima", "anima-fast", "lora") },
  { path: "/lora/anima-fast", redirect: () => trainingQuery("anima", "anima-fast", "lora") },
  { path: "/lora/anima-finetune.html", redirect: () => trainingQuery("anima", "kohya", "finetune") },
  { path: "/dreambooth/index.html", redirect: () => trainingQuery("sdxl", "kohya", "finetune") },
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
  { path: "/lora/tools.html", component: ToolsPage, meta: { titleKey: "tools.title" } },
  { path: "/lora/params.html", component: ParamsPage, meta: { titleKey: "paramsPage.title" } },
  {
    path: "/tageditor.html",
    component: IntegrationPage,
    props: { titleKey: "integration.legacyTagEditor", src: "/proxy/tageditor/" },
    meta: { titleKey: "integration.legacyTagEditor" },
  },
  { path: "/:pathMatch(.*)*", component: NotFoundPage, meta: { titleKey: "notFound.title" } },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

router.afterEach((route) => {
  const titleKey = typeof route.meta.titleKey === "string" ? route.meta.titleKey : "app.brand"
  document.title = `${i18n.global.t(titleKey)} | ${i18n.global.t("app.brand")}`
})

export default router
