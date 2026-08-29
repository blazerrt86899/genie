import { create } from "zustand";

export type TaskStatus = "todo" | "in_progress" | "done";

export interface Task {
  id: string;
  title: string;
  description?: string;
  status: TaskStatus;
}

interface TaskState {
  tasks: Task[];
  setTasks: (tasks: Task[]) => void;
  upsertTask: (task: Task) => void;
  moveTask: (id: string, status: TaskStatus) => void;
}

export const useTaskStore = create<TaskState>((set) => ({
  tasks: [],
  setTasks: (tasks) => set({ tasks }),
  upsertTask: (task) =>
    set((s) => {
      const exists = s.tasks.some((t) => t.id === task.id);
      return {
        tasks: exists
          ? s.tasks.map((t) => (t.id === task.id ? task : t))
          : [...s.tasks, task],
      };
    }),
  moveTask: (id, status) =>
    set((s) => ({
      tasks: s.tasks.map((t) => (t.id === id ? { ...t, status } : t)),
    })),
}));
