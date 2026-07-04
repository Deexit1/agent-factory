import { ACTOR_ROLES, useActor } from "./ActorContext";

export function ActorSwitcher(): React.JSX.Element {
  const { actor, role, setActor, setRole } = useActor();

  return (
    <div className="flex items-center gap-2 text-sm">
      <label className="flex items-center gap-1">
        <span className="text-gray-500">Acting as</span>
        <input
          className="rounded border border-gray-300 px-2 py-1"
          value={actor}
          onChange={(event) => setActor(event.target.value)}
          aria-label="Actor id"
        />
      </label>
      <label className="flex items-center gap-1">
        <span className="text-gray-500">Role</span>
        <select
          className="rounded border border-gray-300 px-2 py-1"
          value={role}
          onChange={(event) => setRole(event.target.value as (typeof ACTOR_ROLES)[number])}
          aria-label="Actor role"
        >
          {ACTOR_ROLES.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}
