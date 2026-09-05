import { useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, ApiRequestError, formatPaise } from "../lib/api";

declare global {
  interface Window {
    Razorpay?: new (options: Record<string, unknown>) => { open: () => void };
  }
}

interface IntentResponse {
  intent_id: string;
  razorpay_order_id: string;
  amount_paise: number;
  razorpay_key_id: string;
}

interface PaymentsConfig {
  razorpay_key_id: string;
}

/** docs/04: must call POST /payments/intent first, then open Checkout with
 * the returned order_id — never open Checkout with a client-computed
 * amount alone. Never optimistically render the new rank before the
 * webhook has landed; only navigation/query invalidation after settlement
 * confirms it (docs/04's "resisting the urge to feel instant"). */
export function BidModal({
  projectId,
  projectName,
  currentTotalPaise,
  minToTakeLeadPaise,
  onClose,
}: {
  projectId: string;
  projectName: string;
  currentTotalPaise: number;
  minToTakeLeadPaise: number | null;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [amountRupees, setAmountRupees] = useState(
    minToTakeLeadPaise ? Math.ceil(minToTakeLeadPaise / 100).toString() : "",
  );
  const [status, setStatus] = useState<"idle" | "processing" | "confirming" | "error">("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Check whether real Razorpay Checkout is even available *before*
  // attempting anything — POST /payments/intent hard-requires Razorpay
  // credentials server-side and has no reason to be called at all when
  // there aren't any (see app/routers/payments.py's /config endpoint).
  const { data: paymentsConfig } = useQuery({
    queryKey: ["payments-config"],
    queryFn: () => apiFetch<PaymentsConfig>("/payments/config"),
    staleTime: Infinity,
  });

  async function invalidateAndClose() {
    await queryClient.invalidateQueries({ queryKey: ["project", projectId] });
    await queryClient.invalidateQueries({ queryKey: ["leaderboard"] });
    onClose();
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setStatus("processing");
    setErrorMessage(null);

    const amountPaise = Math.round(parseFloat(amountRupees) * 100);
    if (!Number.isFinite(amountPaise) || amountPaise <= 0) {
      setStatus("error");
      setErrorMessage("Enter a valid amount.");
      return;
    }

    const idempotencyKey = crypto.randomUUID();

    try {
      if (window.Razorpay && paymentsConfig?.razorpay_key_id) {
        const intent = await apiFetch<IntentResponse>("/payments/intent", {
          method: "POST",
          body: JSON.stringify({ project_id: projectId, amount_paise: amountPaise, idempotency_key: idempotencyKey }),
        });

        const checkout = new window.Razorpay({
          key: intent.razorpay_key_id,
          amount: intent.amount_paise,
          currency: "INR",
          order_id: intent.razorpay_order_id,
          name: projectName,
          handler: () => {
            // UX hint only — the webhook is the only source of truth
            // (docs/00 non-negotiable #2). Just move to "confirming".
            setStatus("confirming");
            queryClient.invalidateQueries({ queryKey: ["project", projectId] });
          },
          modal: { ondismiss: () => setStatus("idle") },
        });
        checkout.open();
        return;
      }

      // No live Razorpay integration available — settle via the demo path
      // (docs/02's POST /payments/mock), never through /payments/intent.
      setStatus("confirming");
      await apiFetch("/payments/mock", {
        method: "POST",
        body: JSON.stringify({ project_id: projectId, amount_paise: amountPaise, idempotency_key: idempotencyKey }),
      });
      await invalidateAndClose();
    } catch (err) {
      setStatus("error");
      if (err instanceof ApiRequestError) {
        if (err.code === "RATE_LIMITED") {
          setErrorMessage("Too many attempts — try again in a while.");
        } else if (err.code === "AMOUNT_TOO_LOW") {
          setErrorMessage("That amount is too low.");
        } else if (err.code === "PROJECT_NOT_LIVE") {
          setErrorMessage("This project is no longer accepting bids.");
        } else {
          setErrorMessage(err.message);
        }
      } else {
        setErrorMessage("Something went wrong. Please try again.");
      }
    }
  }

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true">
      <div className="modal">
        <h2>Place a bid on {projectName}</h2>
        <p>Current total: {formatPaise(currentTotalPaise)}</p>
        {minToTakeLeadPaise !== null && (
          <p>Minimum to take #1: {formatPaise(minToTakeLeadPaise)}</p>
        )}

        {status === "confirming" ? (
          <p role="status">Confirming your bid…</p>
        ) : (
          <form onSubmit={handleSubmit}>
            <label htmlFor="bid-amount">Amount (₹)</label>
            <input
              id="bid-amount"
              type="number"
              inputMode="decimal"
              min={1}
              step="1"
              value={amountRupees}
              onChange={(e) => setAmountRupees(e.target.value)}
              required
            />
            {errorMessage && (
              <p role="alert" className="form-error">
                {errorMessage}
              </p>
            )}
            <div className="modal-actions">
              <button type="button" onClick={onClose}>
                Cancel
              </button>
              <button type="submit" disabled={status === "processing"}>
                {status === "processing" ? "Processing…" : "Pay & bid"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
