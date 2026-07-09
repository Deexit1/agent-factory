import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useAuth } from "@/auth/AuthContext";
import { useMyOrgs, useSwitchOrg } from "@/api/queries";

export function OrgSwitcher(): React.JSX.Element | null {
  const { orgId, setToken } = useAuth();
  const { data: orgs } = useMyOrgs();
  const switchOrg = useSwitchOrg();

  if (!orgs || orgs.items.length <= 1) {
    return null;
  }

  return (
    <Select
      value={orgId ?? ""}
      onValueChange={(value) => {
        if (!value) return;
        void switchOrg.mutateAsync({ orgId: value }).then((session) => setToken(session.token));
      }}
    >
      <SelectTrigger aria-label="Switch org" size="sm">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {orgs.items.map((org) => (
          <SelectItem key={org.id} value={org.id}>
            {org.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
