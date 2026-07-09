import { Link } from "@tanstack/react-router";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Separator } from "@/components/ui/separator";
import { useAuth } from "@/auth/AuthContext";
import { OrgSwitcher } from "@/shell/OrgSwitcher";

const NAV_LINKS = [
  { to: "/board", label: "Board" },
  { to: "/planning", label: "Planning" },
  { to: "/assignments", label: "Assignments" },
  { to: "/dashboard", label: "Dashboard" },
  { to: "/keys", label: "Keys" },
  { to: "/repos", label: "Repos" },
  { to: "/docs", label: "Docs" },
  { to: "/billing", label: "Billing" },
  { to: "/members", label: "Members" },
] as const;

const STAFF_NAV_LINKS = [
  { to: "/admin/impersonate", label: "Staff" },
  { to: "/admin/intake", label: "Intake" },
  { to: "/admin/strikes", label: "Strikes" },
  { to: "/admin/funnel", label: "Funnel" },
] as const;

const linkClassName =
  "shrink-0 text-sm text-muted-foreground transition-colors hover:text-foreground [&.active]:font-semibold [&.active]:text-foreground";

export function TopNav(): React.JSX.Element {
  const { actor, isPlatformStaff, impersonating, logout } = useAuth();

  return (
    <nav className="flex items-center justify-between gap-4 border-b px-4 py-2">
      <div className="flex min-w-0 items-center gap-4 overflow-x-auto">
        {NAV_LINKS.map((link) => (
          <Link key={link.to} to={link.to} className={linkClassName}>
            {link.label}
          </Link>
        ))}
        {isPlatformStaff && !impersonating && (
          <>
            <Separator orientation="vertical" className="h-4" />
            {STAFF_NAV_LINKS.map((link) => (
              <Link key={link.to} to={link.to} className={linkClassName}>
                {link.label}
              </Link>
            ))}
          </>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-3">
        <OrgSwitcher />
        <DropdownMenu>
          <DropdownMenuTrigger className="flex items-center gap-2 text-sm text-muted-foreground outline-none hover:text-foreground">
            <Avatar size="sm">
              <AvatarFallback>{(actor ?? "?").slice(0, 1).toUpperCase()}</AvatarFallback>
            </Avatar>
            {actor}
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={logout}>Sign out</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </nav>
  );
}
