import { defineComponent, h, onMounted, ref } from "vue";

interface TaskItem {
  id: string;
  status: string;
  command?: string;
}

function isRunning(status: string) {
  return status.toUpperCase() === "RUNNING";
}

export const TaskPage = defineComponent({
  name: "TaskPage",
  setup() {
    const tasks = ref<TaskItem[]>([]);
    const status = ref("Loading tasks...");

    async function refreshTasks() {
      status.value = "Loading tasks...";
      try {
        const response = await fetch("/api/tasks");
        const payload = await response.json();
        tasks.value = payload.data?.tasks ?? [];
        status.value = tasks.value.length ? `${tasks.value.length} task(s) loaded` : "No known tasks";
      } catch {
        tasks.value = [];
        status.value = "Unable to load tasks";
      }
    }

    async function terminateTask(taskId: string) {
      status.value = `Terminating ${taskId}...`;
      try {
        await fetch(`/api/tasks/terminate/${encodeURIComponent(taskId)}`);
        await refreshTasks();
      } catch {
        status.value = `Unable to terminate ${taskId}`;
      }
    }

    onMounted(refreshTasks);

    return () =>
      h("main", { class: "content task-page" }, [
        h("header", { class: "task-header" }, [
          h("div", [
            h("p", { class: "eyebrow" }, "Runtime"),
            h("h1", "Tasks"),
            h("p", { class: "summary" }, "Source-owned task monitor for training jobs started in this server session."),
          ]),
          h("button", { type: "button", class: "source-static-action", onClick: refreshTasks }, "Refresh Tasks"),
        ]),
        h("section", { class: "task-monitor", "aria-label": "Task monitor" }, [
          h("p", { class: "task-status" }, status.value),
          tasks.value.length
            ? h(
                "div",
                { class: "task-list" },
                tasks.value.map((task) =>
                  h("article", { class: `task-card task-card--${task.status.toLowerCase()}` }, [
                    h("div", { class: "task-card__main" }, [
                      h("span", { class: "task-card__status" }, task.status),
                      h("strong", task.id),
                      task.command ? h("code", task.command) : null,
                    ]),
                    h("div", { class: "task-card__actions" }, [
                      h("a", { href: `/train-log?task_id=${encodeURIComponent(task.id)}` }, "Open Log"),
                      h("a", { href: `/api/train/log/tail/${encodeURIComponent(task.id)}` }, "Tail API"),
                      isRunning(task.status)
                        ? h(
                            "button",
                            {
                              type: "button",
                              "data-task-action": "terminate",
                              onClick: () => terminateTask(task.id),
                            },
                            "Terminate",
                          )
                        : null,
                    ]),
                  ]),
                ),
              )
            : h("div", { class: "task-empty" }, [
                h("strong", "No tasks are currently known."),
                h("span", "Start a training job from an Anima route and refresh this page to see it here."),
              ]),
        ]),
      ]);
  },
});
