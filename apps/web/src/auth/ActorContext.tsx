import { createContext, useContext, useMemo, useState } from "react";

import type { ActorContext as ApiActorContext } from "../api/client";

const STORAGE_KEY = "agent-factory:actor-context";

const ROLES = ["viewer", "approver", "admin"] as const;
export type Role = (typeof ROLES)[number];

interface ActorContextValue extends ApiActorContext {
  role: Role;
  setActor: (actor: string) => void;
  setRole: (role: Role) => void;
}

function loadStoredContext(): ApiActorContext & { role: Role } {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (raw) {
    try {
      const parsed: unknown = JSON.parse(raw);
      if (
        parsed &&
        typeof parsed === "object" &&
        "actor" in parsed &&
        "role" in parsed &&
        typeof parsed.actor === "string" &&
        ROLES.includes(parsed.role as Role)
      ) {
        return { actor: parsed.actor, role: parsed.role as Role };
      }
    } catch {
      // fall through to default
    }
  }
  return { actor: "human:anonymous", role: "viewer" };
}

const ActorReactContext = createContext<ActorContextValue | null>(null);

export function ActorProvider({ children }: { children: React.ReactNode }): React.JSX.Element {
  const [{ actor, role }, setState] = useState(loadStoredContext);

  const value = useMemo<ActorContextValue>(
    () => ({
      actor,
      role,
      setActor: (nextActor: string) => {
        setState((prev) => {
          const next = { ...prev, actor: nextActor };
          localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
          return next;
        });
      },
      setRole: (nextRole: Role) => {
        setState((prev) => {
          const next = { ...prev, role: nextRole };
          localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
          return next;
        });
      },
    }),
    [actor, role],
  );

  return <ActorReactContext.Provider value={value}>{children}</ActorReactContext.Provider>;
}

export function useActor(): ActorContextValue {
  const context = useContext(ActorReactContext);
  if (!context) {
    throw new Error("useActor must be used within an ActorProvider");
  }
  return context;
}

export const ACTOR_ROLES = ROLES;
