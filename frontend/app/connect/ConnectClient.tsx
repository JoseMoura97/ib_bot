"use client";

import { useState } from "react";
import { Button } from "../_components/ui/Button";
import { Card, CardContent } from "../_components/ui/Card";
import { Input } from "../_components/ui/Input";
import { cn } from "../_components/cn";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type Step = 0 | 1 | 2 | 3;

type SessionStatus = {
  session_id: string;
  port: number;
  ibeam_response?: {
    authenticated?: boolean;
    competing?: boolean;
    message?: string;
  };
};

type ConnectedSession = {
  session_id: string;
  port: number;
  container_name: string;
  status: string;
};

// ---------------------------------------------------------------------------
// Step metadata
// ---------------------------------------------------------------------------

const STEPS = [
  { label: "Open IB Account", short: "Account" },
  { label: "Enable Authenticator", short: "2FA" },
  { label: "Copy Secret Key", short: "Secret" },
  { label: "Connect", short: "Connect" },
];

// ---------------------------------------------------------------------------
// Helper: poll session status
// ---------------------------------------------------------------------------

async function pollUntilAuthenticated(
  accountId: string,
  onTick: (msg: string) => void,
  maxAttempts = 20,
  intervalMs = 6000,
): Promise<SessionStatus> {
  for (let i = 0; i < maxAttempts; i++) {
    await new Promise((r) => setTimeout(r, intervalMs));
    onTick(`Waiting for login… (${(i + 1) * Math.round(intervalMs / 1000)}s / ~120s)`);
    try {
      const res = await fetch(`/api/sessions/${encodeURIComponent(accountId)}/status`, {
        cache: "no-store",
      });
      if (!res.ok) continue;
      const data = (await res.json()) as SessionStatus;
      if (data?.ibeam_response?.authenticated) return data;
    } catch {
      // keep polling
    }
  }
  throw new Error("Authentication timed out after ~2 minutes. Check your credentials and TOTP secret.");
}

// ---------------------------------------------------------------------------
// Step components
// ---------------------------------------------------------------------------

function StepIndicator({ current }: { current: Step }) {
  return (
    <nav aria-label="Progress" className="mb-6">
      <ol className="flex items-center gap-0">
        {STEPS.map((s, i) => {
          const done = i < current;
          const active = i === current;
          return (
            <li key={i} className="flex flex-1 items-center">
              <div className="flex flex-col items-center gap-1">
                <span
                  className={cn(
                    "flex h-8 w-8 items-center justify-center rounded-full border-2 text-sm font-semibold transition-colors",
                    done && "border-emerald-500 bg-emerald-500 text-white",
                    active && "border-primary bg-primary text-primary-foreground",
                    !done && !active && "border-muted-foreground/30 text-muted-foreground",
                  )}
                >
                  {done ? (
                    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                    </svg>
                  ) : (
                    i + 1
                  )}
                </span>
                <span
                  className={cn(
                    "hidden text-xs font-medium sm:block",
                    active ? "text-foreground" : "text-muted-foreground",
                  )}
                >
                  {s.short}
                </span>
              </div>
              {i < STEPS.length - 1 && (
                <div
                  className={cn(
                    "mx-2 h-px flex-1 transition-colors",
                    i < current ? "bg-emerald-500" : "bg-muted-foreground/20",
                  )}
                />
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

function StepCard({ children, title, subtitle }: { children: React.ReactNode; title: string; subtitle?: string }) {
  return (
    <Card className="shadow-none">
      <CardContent className="space-y-4 py-6">
        <div>
          <h2 className="text-lg font-semibold">{title}</h2>
          {subtitle && <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>}
        </div>
        {children}
      </CardContent>
    </Card>
  );
}

function InstructionList({ items }: { items: Array<{ num: number; text: React.ReactNode }> }) {
  return (
    <ol className="space-y-3">
      {items.map((item) => (
        <li key={item.num} className="flex gap-3">
          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-bold text-primary">
            {item.num}
          </span>
          <span className="text-sm leading-relaxed text-muted-foreground">{item.text}</span>
        </li>
      ))}
    </ol>
  );
}

// ---------------------------------------------------------------------------
// Step 0: Open IB Account
// ---------------------------------------------------------------------------

function Step0({ onNext }: { onNext: () => void }) {
  return (
    <StepCard
      title="Open an Interactive Brokers Account"
      subtitle="You'll need an individual IBKR account with paper or live trading enabled."
    >
      <InstructionList
        items={[
          {
            num: 1,
            text: (
              <>
                Go to{" "}
                <a
                  href="https://www.interactivebrokers.com/en/trading/open-account.php"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-medium text-primary underline underline-offset-2"
                >
                  interactivebrokers.com
                </a>{" "}
                and click <strong>Open Account</strong>.
              </>
            ),
          },
          {
            num: 2,
            text: (
              <>
                Complete the registration form. Choose <strong>Individual</strong> account type. Use your real
                identity — IBKR does full KYC verification.
              </>
            ),
          },
          {
            num: 3,
            text: (
              <>
                Upload the required identity documents (passport or national ID + proof of address). Approval
                typically takes <strong>1 business day</strong>.
              </>
            ),
          },
          {
            num: 4,
            text: (
              <>
                Once approved, log into the{" "}
                <a
                  href="https://client.ibkr.com"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-medium text-primary underline underline-offset-2"
                >
                  Client Portal
                </a>{" "}
                and fund your account (minimum $0 for cash accounts).
              </>
            ),
          },
          {
            num: 5,
            text: (
              <>
                Write down your <strong>IBKR username</strong> (e.g. <code className="rounded bg-muted px-1 text-xs">john.smith</code>
                ) — you&apos;ll need it in Step 4.
              </>
            ),
          },
        ]}
      />

      <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-sm text-amber-700 dark:text-amber-400">
        <strong>Already have an account?</strong> Skip ahead — you just need to complete Steps 2 and 3.
      </div>

      <div className="flex justify-end">
        <Button variant="primary" onClick={onNext}>
          I have an account →
        </Button>
      </div>
    </StepCard>
  );
}

// ---------------------------------------------------------------------------
// Step 1: Enable Authenticator App
// ---------------------------------------------------------------------------

function Step1({ onNext, onBack }: { onNext: () => void; onBack: () => void }) {
  return (
    <StepCard
      title="Enable the Mobile Authenticator App"
      subtitle="IB Bot uses TOTP (Time-based One-Time Passwords) to log in automatically on your behalf."
    >
      <InstructionList
        items={[
          {
            num: 1,
            text: (
              <>
                Log into the{" "}
                <a
                  href="https://client.ibkr.com"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-medium text-primary underline underline-offset-2"
                >
                  IBKR Client Portal
                </a>
                .
              </>
            ),
          },
          {
            num: 2,
            text: (
              <>
                Click your name (top right) → <strong>Settings</strong> → <strong>Security</strong> →{" "}
                <strong>Two-Factor Authentication</strong>.
              </>
            ),
          },
          {
            num: 3,
            text: (
              <>
                Under <em>Secure Login System</em>, click <strong>Add a Method</strong> and choose{" "}
                <strong>Mobile Authenticator App</strong>.
              </>
            ),
          },
          {
            num: 4,
            text: (
              <>
                Install{" "}
                <strong>Google Authenticator</strong>, <strong>Authy</strong>, or any TOTP-compatible app
                on your phone.
              </>
            ),
          },
          {
            num: 5,
            text: (
              <>
                IBKR will show you a QR code. <strong>Before</strong> scanning it, click{" "}
                <em>&ldquo;Can&apos;t scan? Enter code manually&rdquo;</em> (or similar). This reveals the{" "}
                <strong>secret key</strong> — you&apos;ll copy it in the next step.
              </>
            ),
          },
          {
            num: 6,
            text: <>Scan the QR code (or enter the key) in your authenticator app and confirm the 6-digit code to finish setup.</>,
          },
        ]}
      />

      <div className="rounded-lg border border-blue-500/30 bg-blue-500/5 p-3 text-sm text-blue-700 dark:text-blue-400">
        <strong>Already have the authenticator app set up?</strong> You&apos;ll need to add it again (or find your existing
        secret key) — IBKR only shows the secret once, during setup.
      </div>

      <div className="flex justify-between">
        <Button variant="outline" onClick={onBack}>
          ← Back
        </Button>
        <Button variant="primary" onClick={onNext}>
          Authenticator is set up →
        </Button>
      </div>
    </StepCard>
  );
}

// ---------------------------------------------------------------------------
// Step 2: Copy Secret Key
// ---------------------------------------------------------------------------

function Step2({ onNext, onBack }: { onNext: () => void; onBack: () => void }) {
  return (
    <StepCard
      title="Copy Your Secret Key"
      subtitle='The "secret key" is the base32 code shown during authenticator setup — it looks like JBSWY3DPEHPK3PXP.'
    >
      <InstructionList
        items={[
          {
            num: 1,
            text: (
              <>
                During authenticator setup, IBKR shows a QR code. Click <em>&ldquo;Enter code manually&rdquo;</em> or{" "}
                <em>&ldquo;Show secret key&rdquo;</em> to reveal the <strong>base32 text code</strong>.
              </>
            ),
          },
          {
            num: 2,
            text: (
              <>
                It looks like: <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs tracking-wider">
                  3LIWICNOAIU3D6WOL3627WN3A3HGDEBP
                </code>
                {" "}— uppercase letters and numbers, ~32 characters.
              </>
            ),
          },
          {
            num: 3,
            text: (
              <>
                <strong>Copy and save this key somewhere safe</strong> (password manager recommended). IBKR
                only shows it once.
              </>
            ),
          },
          {
            num: 4,
            text: (
              <>
                You&apos;ll paste this in the next step. IB Bot uses it to generate the 6-digit TOTP codes that
                IBKR requires to log in — the same codes your authenticator app generates.
              </>
            ),
          },
        ]}
      />

      <div className="rounded-lg border border-red-500/30 bg-red-500/5 p-3 text-sm text-red-700 dark:text-red-400">
        <strong>Security note:</strong> Your secret key is transmitted over HTTPS and stored only in the
        running session container — never written to disk. You can disconnect at any time from this page.
      </div>

      <div className="flex justify-between">
        <Button variant="outline" onClick={onBack}>
          ← Back
        </Button>
        <Button variant="primary" onClick={onNext}>
          I have my secret key →
        </Button>
      </div>
    </StepCard>
  );
}

// ---------------------------------------------------------------------------
// Step 3: Connect form
// ---------------------------------------------------------------------------

function Step3({
  onConnected,
  onBack,
}: {
  onConnected: (session: ConnectedSession) => void;
  onBack: () => void;
}) {
  const [account, setAccount] = useState("");
  const [password, setPassword] = useState("");
  const [totpSecret, setTotpSecret] = useState("");
  const [connecting, setConnecting] = useState(false);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleConnect() {
    setError(null);
    setStatusMsg(null);
    setConnecting(true);

    try {
      // 1. Create the session
      setStatusMsg("Starting IB gateway container…");
      const res = await fetch("/api/sessions/connect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ib_account: account.trim(),
          ib_password: password,
          totp_secret: totpSecret.trim().toUpperCase().replace(/\s+/g, ""),
        }),
      });

      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || `HTTP ${res.status}`);
      }

      const created = await res.json();
      setStatusMsg("Container started. Logging in with your credentials…");

      // 2. Poll for authenticated status
      const authStatus = await pollUntilAuthenticated(created.session_id ?? account.trim(), setStatusMsg);

      onConnected({
        session_id: authStatus.session_id,
        port: authStatus.port,
        container_name: created.container_name,
        status: "authenticated",
      });
    } catch (e: any) {
      setError(String(e?.message ?? e));
    } finally {
      setConnecting(false);
      if (!error) setStatusMsg(null);
    }
  }

  const canSubmit = account.trim() && password && totpSecret.trim().length >= 16;

  return (
    <StepCard
      title="Connect Your Account"
      subtitle="Enter your IBKR credentials. They are sent directly to your dedicated gateway container and never stored."
    >
      <div className="space-y-4">
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-muted-foreground">IBKR Username</label>
          <Input
            value={account}
            onChange={(e) => setAccount(e.target.value)}
            placeholder="e.g. john.smith"
            disabled={connecting}
            autoComplete="username"
          />
        </div>

        <div className="space-y-1.5">
          <label className="text-xs font-medium text-muted-foreground">IBKR Password</label>
          <Input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Your IBKR password"
            disabled={connecting}
            autoComplete="current-password"
          />
        </div>

        <div className="space-y-1.5">
          <label className="text-xs font-medium text-muted-foreground">Authenticator Secret Key (base32)</label>
          <Input
            value={totpSecret}
            onChange={(e) => setTotpSecret(e.target.value)}
            placeholder="e.g. JBSWY3DPEHPK3PXP…"
            disabled={connecting}
            autoComplete="off"
            className="font-mono tracking-wider"
          />
          <p className="text-xs text-muted-foreground">
            The ~32-character base32 code from Step 3, not a 6-digit TOTP code.
          </p>
        </div>

        {connecting && (
          <div className="flex items-center gap-3 rounded-lg border bg-muted/40 px-4 py-3">
            <svg className="h-4 w-4 animate-spin text-primary" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z" />
            </svg>
            <span className="text-sm text-muted-foreground">{statusMsg ?? "Connecting…"}</span>
          </div>
        )}

        {error && (
          <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {error}
          </div>
        )}
      </div>

      <div className="flex justify-between pt-2">
        <Button variant="outline" onClick={onBack} disabled={connecting}>
          ← Back
        </Button>
        <Button variant="primary" onClick={handleConnect} disabled={!canSubmit || connecting}>
          {connecting ? "Connecting…" : "Connect Account"}
        </Button>
      </div>
    </StepCard>
  );
}

// ---------------------------------------------------------------------------
// Success state
// ---------------------------------------------------------------------------

function SuccessCard({
  session,
  onDisconnect,
}: {
  session: ConnectedSession;
  onDisconnect: () => void;
}) {
  const [disconnecting, setDisconnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleDisconnect() {
    setDisconnecting(true);
    setError(null);
    try {
      const res = await fetch(`/api/sessions/${encodeURIComponent(session.session_id)}`, {
        method: "DELETE",
      });
      if (!res.ok) throw new Error(await res.text());
      onDisconnect();
    } catch (e: any) {
      setError(String(e?.message ?? e));
    } finally {
      setDisconnecting(false);
    }
  }

  return (
    <Card className="border-emerald-500/40 shadow-none">
      <CardContent className="space-y-4 py-6">
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-full bg-emerald-500/15">
            <svg className="h-5 w-5 text-emerald-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
            </svg>
          </span>
          <div>
            <div className="font-semibold text-emerald-600 dark:text-emerald-400">Account connected!</div>
            <div className="text-sm text-muted-foreground">
              IB gateway is running and authenticated for{" "}
              <code className="rounded bg-muted px-1 font-mono text-xs">{session.session_id}</code>
            </div>
          </div>
        </div>

        <div className="rounded-lg border bg-muted/30 p-3 font-mono text-xs text-muted-foreground">
          <div>Container: {session.container_name}</div>
          <div>Internal port: {session.port}</div>
          <div>Status: authenticated ✓</div>
        </div>

        <p className="text-sm text-muted-foreground">
          Your account is now connected and will auto-trade according to your strategy allocations. The gateway
          session is kept alive automatically every 55 seconds. You can disconnect at any time.
        </p>

        {error && (
          <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {error}
          </div>
        )}

        <div className="flex flex-wrap gap-2">
          <a href="/live">
            <Button variant="primary">View Live Trading →</Button>
          </a>
          <Button variant="outline" className="text-red-500 hover:border-red-500/50" onClick={handleDisconnect} disabled={disconnecting}>
            {disconnecting ? "Disconnecting…" : "Disconnect"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Active sessions panel
// ---------------------------------------------------------------------------

function ActiveSessionsPanel() {
  const [sessions, setSessions] = useState<ConnectedSession[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const res = await fetch("/api/sessions", { cache: "no-store" });
      const data = await res.json();
      setSessions(data ?? []);
    } catch {
      setSessions([]);
    } finally {
      setLoading(false);
    }
  }

  async function handleDisconnect(accountId: string) {
    await fetch(`/api/sessions/${encodeURIComponent(accountId)}`, { method: "DELETE" });
    await load();
  }

  return (
    <details
      className="rounded-xl border bg-card shadow-none"
      open={open}
      onToggle={(e) => {
        const isOpen = (e.target as HTMLDetailsElement).open;
        setOpen(isOpen);
        if (isOpen && sessions === null) load();
      }}
    >
      <summary className="cursor-pointer px-4 py-3 text-sm font-semibold">Active sessions</summary>
      <div className="border-t px-4 py-4">
        <div className="mb-3 flex justify-end">
          <Button size="sm" variant="outline" onClick={load} disabled={loading}>
            {loading ? "Loading…" : "Refresh"}
          </Button>
        </div>
        {sessions === null ? (
          <p className="text-sm text-muted-foreground">Click refresh to load.</p>
        ) : sessions.length === 0 ? (
          <p className="text-sm text-muted-foreground">No active sessions.</p>
        ) : (
          <div className="space-y-2">
            {sessions.map((s: any) => (
              <div key={s.session_id} className="flex items-center justify-between gap-3 rounded-lg border px-3 py-2">
                <div>
                  <span className="font-mono text-sm font-semibold">{s.session_id}</span>
                  <span
                    className={cn(
                      "ml-2 rounded-full px-2 py-0.5 text-xs font-medium",
                      s.status === "authenticated"
                        ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400"
                        : "bg-muted text-muted-foreground",
                    )}
                  >
                    {s.status}
                  </span>
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  className="text-red-500 hover:border-red-500/50"
                  onClick={() => handleDisconnect(s.session_id)}
                >
                  Disconnect
                </Button>
              </div>
            ))}
          </div>
        )}
      </div>
    </details>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function ConnectClient() {
  const [step, setStep] = useState<Step>(0);
  const [connectedSession, setConnectedSession] = useState<ConnectedSession | null>(null);

  function handleConnected(session: ConnectedSession) {
    setConnectedSession(session);
    setStep(3); // stay on step 3 but show success
  }

  function handleDisconnect() {
    setConnectedSession(null);
    setStep(0);
  }

  return (
    <div className="space-y-4">
      <StepIndicator current={step} />

      {connectedSession ? (
        <SuccessCard session={connectedSession} onDisconnect={handleDisconnect} />
      ) : (
        <>
          {step === 0 && <Step0 onNext={() => setStep(1)} />}
          {step === 1 && <Step1 onNext={() => setStep(2)} onBack={() => setStep(0)} />}
          {step === 2 && <Step2 onNext={() => setStep(3)} onBack={() => setStep(1)} />}
          {step === 3 && <Step3 onConnected={handleConnected} onBack={() => setStep(2)} />}
        </>
      )}

      <ActiveSessionsPanel />
    </div>
  );
}
