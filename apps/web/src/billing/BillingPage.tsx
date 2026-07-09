import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useAuth } from "@/auth/AuthContext";
import { useBillingUsage, useOrgBilling } from "@/api/queries";
import type { BillingStatus } from "@/api/types";

function statusVariant(status: BillingStatus): "default" | "destructive" {
  return status === "active" ? "default" : "destructive";
}

function formatInr(amount: number): string {
  return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" }).format(amount);
}

function formatDate(value: string | null): string | null {
  return value ? new Date(value).toLocaleDateString() : null;
}

export function BillingPage(): React.JSX.Element {
  const { orgId } = useAuth();
  const { data: billing, isLoading: billingLoading } = useOrgBilling(orgId);
  const { data: usage, isLoading: usageLoading } = useBillingUsage(orgId);

  return (
    <main className="mx-auto max-w-3xl p-6">
      <h1 className="text-xl font-bold text-foreground">Billing</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Read-only view of your org's plan and usage for the current period.
      </p>

      <Card className="mt-4">
        <CardHeader>
          <CardTitle className="flex items-center justify-between text-base">
            Plan
            {billing && <Badge variant={statusVariant(billing.billing_status)}>{billing.billing_status}</Badge>}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {billingLoading || !billing ? (
            <Skeleton className="h-16 w-full" />
          ) : (
            <div className="flex flex-col gap-1 text-sm">
              <div>
                Plan: <span className="font-medium">{billing.plan}</span>
                {billing.pending_plan && (
                  <span className="text-muted-foreground">
                    {" "}
                    (switching to {billing.pending_plan}
                    {formatDate(billing.pending_plan_effective_at)
                      ? ` on ${formatDate(billing.pending_plan_effective_at)}`
                      : ""}
                    )
                  </span>
                )}
              </div>
              {billing.current_period_end && (
                <div className="text-muted-foreground">
                  Current period ends {formatDate(billing.current_period_end)}
                </div>
              )}
              {billing.dunning_grace_until && (
                <div className="text-destructive">
                  Payment overdue — access pauses after {formatDate(billing.dunning_grace_until)}
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      <Card className="mt-4">
        <CardHeader>
          <CardTitle className="text-base">Usage this period</CardTitle>
        </CardHeader>
        <CardContent>
          {usageLoading || !usage ? (
            <Skeleton className="h-32 w-full" />
          ) : (
            <>
              <p className="mb-3 text-xs text-muted-foreground">
                {formatDate(usage.period_start)} – {formatDate(usage.period_end)} · {usage.plan_key} plan
              </p>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Item</TableHead>
                    <TableHead className="text-right">Included</TableHead>
                    <TableHead className="text-right">Used</TableHead>
                    <TableHead className="text-right">Overage</TableHead>
                    <TableHead className="text-right">Amount</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {usage.line_items.map((line) => (
                    <TableRow key={line.kind}>
                      <TableCell className="font-medium">{line.kind}</TableCell>
                      <TableCell className="text-right">{line.included}</TableCell>
                      <TableCell className="text-right">{line.used}</TableCell>
                      <TableCell className="text-right">{line.overage}</TableCell>
                      <TableCell className="text-right">{formatInr(line.amount_inr)}</TableCell>
                    </TableRow>
                  ))}
                  {usage.line_items.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={5} className="text-center text-muted-foreground">
                        No usage recorded for this period.
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
                <TableFooter>
                  <TableRow>
                    <TableCell colSpan={4}>Base fee + total</TableCell>
                    <TableCell className="text-right">{formatInr(usage.total_inr)}</TableCell>
                  </TableRow>
                </TableFooter>
              </Table>
            </>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
