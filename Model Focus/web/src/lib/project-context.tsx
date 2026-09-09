"use client";

import { createContext, ReactNode, useCallback, useContext, useEffect, useState } from "react";
import { api, Project } from "@/lib/api";

const STORAGE_KEY = "biscuits-focus:active-project";

type ProjectContextValue = {
  projectId: string | null;
  project: Project | null;
  projects: Project[];
  loading: boolean;
  setProjectId: (id: string) => void;
  refresh: () => void;
};

const ProjectContext = createContext<ProjectContextValue | null>(null);

export function ProjectProvider({ children }: { children: ReactNode }) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectIdState] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const setProjectId = useCallback((id: string) => {
    setProjectIdState(id);
    if (typeof window !== "undefined") window.localStorage.setItem(STORAGE_KEY, id);
  }, []);

  const refresh = useCallback(() => {
    api.projects.list().then((list) => {
      setProjects(list);
      setLoading(false);
      setProjectIdState((current) => {
        if (current && list.some((proj) => proj.id === current)) return current;
        const stored = typeof window !== "undefined" ? window.localStorage.getItem(STORAGE_KEY) : null;
        const resolved = stored && list.some((proj) => proj.id === stored) ? stored : list[0]?.id ?? null;
        if (resolved && typeof window !== "undefined") window.localStorage.setItem(STORAGE_KEY, resolved);
        return resolved;
      });
    });
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const project = projects.find((proj) => proj.id === projectId) ?? null;

  return (
    <ProjectContext.Provider value={{ projectId, project, projects, loading, setProjectId, refresh }}>
      {children}
    </ProjectContext.Provider>
  );
}

export function useProject(): ProjectContextValue {
  const ctx = useContext(ProjectContext);
  if (!ctx) throw new Error("useProject must be used within a ProjectProvider");
  return ctx;
}
