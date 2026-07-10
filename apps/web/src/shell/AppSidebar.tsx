import {
  BookOpen,
  ClipboardList,
  Flag,
  GitBranch,
  Inbox,
  KanbanSquare,
  KeyRound,
  LayoutDashboard,
  ListTodo,
  Receipt,
  ShieldAlert,
  TrendingUp,
  UserPlus,
} from "lucide-react";
import { Link, useRouterState } from "@tanstack/react-router";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";
import { useAuth } from "@/auth/AuthContext";
import { OrgSwitcher } from "@/shell/OrgSwitcher";

const WORKSPACE_LINKS = [
  { to: "/board", label: "Board", icon: KanbanSquare },
  { to: "/planning", label: "Planning", icon: ListTodo },
  { to: "/assignments", label: "Assignments", icon: ClipboardList },
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
] as const;

const ORG_LINKS = [
  { to: "/keys", label: "Keys", icon: KeyRound },
  { to: "/repos", label: "Repos", icon: GitBranch },
  { to: "/billing", label: "Billing", icon: Receipt },
  { to: "/members", label: "Members", icon: UserPlus },
  { to: "/docs", label: "Docs", icon: BookOpen },
] as const;

const STAFF_LINKS = [
  { to: "/admin/impersonate", label: "Staff", icon: ShieldAlert },
  { to: "/admin/intake", label: "Intake", icon: Inbox },
  { to: "/admin/strikes", label: "Strikes", icon: Flag },
  { to: "/admin/funnel", label: "Funnel", icon: TrendingUp },
] as const;

function NavGroup({
  label,
  links,
  pathname,
}: {
  label: string;
  links: readonly { to: string; label: string; icon: React.ComponentType<{ className?: string }> }[];
  pathname: string;
}): React.JSX.Element {
  return (
    <SidebarGroup>
      <SidebarGroupLabel>{label}</SidebarGroupLabel>
      <SidebarGroupContent>
        <SidebarMenu>
          {links.map((link) => (
            <SidebarMenuItem key={link.to}>
              <SidebarMenuButton isActive={pathname === link.to} render={<Link to={link.to} />}>
                <link.icon />
                <span>{link.label}</span>
              </SidebarMenuButton>
            </SidebarMenuItem>
          ))}
        </SidebarMenu>
      </SidebarGroupContent>
    </SidebarGroup>
  );
}

export function AppSidebar(): React.JSX.Element {
  const { actor, isPlatformStaff, impersonating, logout } = useAuth();
  const pathname = useRouterState({ select: (state) => state.location.pathname });

  return (
    <Sidebar collapsible="none">
      <SidebarHeader className="gap-3 border-b px-3 py-3">
        <span className="px-1 text-sm font-semibold text-sidebar-foreground">Agent Factory</span>
        <OrgSwitcher />
      </SidebarHeader>
      <SidebarContent>
        <NavGroup label="Workspace" links={WORKSPACE_LINKS} pathname={pathname} />
        <NavGroup label="Org" links={ORG_LINKS} pathname={pathname} />
        {isPlatformStaff && !impersonating && (
          <NavGroup label="Staff" links={STAFF_LINKS} pathname={pathname} />
        )}
      </SidebarContent>
      <SidebarFooter className="border-t p-2">
        <DropdownMenu>
          <DropdownMenuTrigger className="flex w-full items-center gap-2 rounded-md p-2 text-left text-sm text-sidebar-foreground outline-none hover:bg-sidebar-accent">
            <Avatar size="sm">
              <AvatarFallback>{(actor ?? "?").slice(0, 1).toUpperCase()}</AvatarFallback>
            </Avatar>
            <span className="min-w-0 flex-1 truncate">{actor}</span>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" side="top">
            <DropdownMenuItem onClick={logout}>Sign out</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarFooter>
    </Sidebar>
  );
}
