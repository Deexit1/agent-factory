import { useState } from "react";

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useAuth } from "@/auth/AuthContext";
import { useInviteMember, useOrgMembers } from "@/api/queries";

const ROLES = ["viewer", "member", "approver", "owner"] as const;

const inviteSchema = z.object({
  email: z.string().email("Enter a valid email"),
  role: z.enum(ROLES),
});

type InviteFormValues = z.infer<typeof inviteSchema>;

function InviteMemberDialog({ orgId }: { orgId: string }): React.JSX.Element {
  const [open, setOpen] = useState(false);
  const inviteMember = useInviteMember();
  const form = useForm<InviteFormValues>({
    resolver: zodResolver(inviteSchema),
    defaultValues: { email: "", role: "member" },
  });

  const onSubmit = async (values: InviteFormValues): Promise<void> => {
    try {
      const invite = await inviteMember.mutateAsync({ orgId, ...values });
      toast.success(`Invite sent to ${values.email}`, {
        description: `${window.location.origin}/invite/${invite.token}`,
      });
      form.reset();
      setOpen(false);
    } catch {
      toast.error("Could not send invite — check the email and try again.");
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button />}>Invite member</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Invite a member</DialogTitle>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={(event) => void form.handleSubmit(onSubmit)(event)} className="flex flex-col gap-4">
            <FormField
              control={form.control}
              name="email"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Email</FormLabel>
                  <FormControl>
                    <Input type="email" placeholder="teammate@example.com" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="role"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Role</FormLabel>
                  <Select value={field.value} onValueChange={field.onChange}>
                    <FormControl>
                      <SelectTrigger className="w-full">
                        <SelectValue />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {ROLES.map((role) => (
                        <SelectItem key={role} value={role}>
                          {role}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />
            <DialogFooter>
              <Button type="submit" disabled={inviteMember.isPending}>
                Send invite
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}

export function OrgMembersPage(): React.JSX.Element {
  const { orgId, role } = useAuth();
  const isOwner = role === "owner";
  const { data: members, isLoading } = useOrgMembers(orgId);

  if (!orgId) {
    return <p className="p-4 text-gray-500">Loading…</p>;
  }

  return (
    <main className="mx-auto max-w-2xl p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-foreground">Members</h1>
          <p className="mt-1 text-sm text-muted-foreground">People with access to this org.</p>
        </div>
        {isOwner && <InviteMemberDialog orgId={orgId} />}
      </div>

      <div className="mt-4">
        {isLoading ? (
          <Skeleton className="h-32 w-full" />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Email</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Joined</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(members?.items ?? []).map((member) => (
                <TableRow key={member.id}>
                  <TableCell className="font-medium">{member.user_email}</TableCell>
                  <TableCell>
                    <Badge variant="outline">{member.role}</Badge>
                  </TableCell>
                  <TableCell>{new Date(member.created_at).toLocaleDateString()}</TableCell>
                </TableRow>
              ))}
              {(members?.items ?? []).length === 0 && (
                <TableRow>
                  <TableCell colSpan={3} className="text-center text-muted-foreground">
                    No members yet.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        )}
      </div>
    </main>
  );
}
