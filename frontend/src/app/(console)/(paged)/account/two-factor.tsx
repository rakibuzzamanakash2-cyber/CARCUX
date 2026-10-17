"use client";

import { useRouter } from "next/navigation";
import { useActionState, useState, useTransition } from "react";

import {
  disableTwoFactor,
  enableTwoFactor,
  newRecoveryCodes,
  type SetupState,
  startTwoFactor,
} from "@/app/actions/two-factor";
import { Field, FormMessage, SubmitButton } from "@/components/form";
import type { TwoFactorStatus } from "@/lib/types";

function RecoveryCodes({ codes }: { codes: string[] }) {
  const router = useRouter();
  return (
    <div className="rounded-md border border-amber/50 bg-amber/10 p-4">
      <p className="text-sm font-semibold">Save these recovery codes now. They are shown once.</p>
      <p className="mt-1 text-sm text-steel">
        Each one lets you sign in once without your phone. Keep them somewhere safe, away from the
        phone (printed, or in a password manager).
      </p>
      <ul className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1 font-mono text-sm">
        {codes.map((c) => (
          <li key={c} className="whitespace-nowrap">
            {c}
          </li>
        ))}
      </ul>
      <button
        type="button"
        className="mt-3 text-sm font-semibold text-brand hover:underline"
        onClick={() => navigator.clipboard?.writeText(codes.join("\n"))}
      >
        Copy all
      </button>
      <button
        type="button"
        className="mt-3 ml-4 rounded-md bg-brand px-3 py-1.5 text-sm font-semibold text-white hover:bg-brand-strong"
        onClick={() => router.refresh()}
      >
        I have saved them
      </button>
    </div>
  );
}

function SetUp() {
  const [setup, setSetup] = useState<SetupState>();
  const [starting, startTransition] = useTransition();
  const [state, action, pending] = useActionState(enableTwoFactor, undefined);

  if (state?.codes) {
    return (
      <div className="flex flex-col gap-4">
        <FormMessage state={state} />
        <RecoveryCodes codes={state.codes} />
      </div>
    );
  }
  if (!setup?.setup) {
    return (
      <div className="flex flex-col gap-3">
        <p className="text-sm">
          Use an authenticator app on your phone (Google Authenticator, Microsoft Authenticator,
          Aegis or similar). After your password, CARCUX will ask for the 6-digit code it shows.
        </p>
        {setup && !setup.ok && <FormMessage state={setup} />}
        <div>
          <button
            type="button"
            disabled={starting}
            onClick={() => startTransition(async () => setSetup(await startTwoFactor()))}
            className="rounded-md bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-strong disabled:opacity-60"
          >
            {starting ? "Starting…" : "Set up two-factor sign-in"}
          </button>
        </div>
      </div>
    );
  }
  const { qr_svg, secret } = setup.setup;
  return (
    <div className="grid gap-5 sm:grid-cols-[auto_1fr] sm:items-start">
      {/* The QR code is drawn by the backend; shown as an image, never as markup. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={`data:image/svg+xml;base64,${btoa(qr_svg)}`}
        alt="QR code to add CARCUX to your authenticator app"
        width={180}
        height={180}
        className="rounded-md border border-line bg-white p-1"
      />
      <form action={action} className="flex max-w-sm flex-col gap-3">
        <p className="text-sm">
          1. Scan the code with the app. Cannot scan? Enter this key by hand:{" "}
          <code className="break-all rounded bg-panel-2 px-1 font-mono text-xs">{secret}</code>
        </p>
        <p className="text-sm">2. Enter the 6-digit code the app shows now.</p>
        <Field
          label="Code"
          name="code"
          type="text"
          inputMode="numeric"
          autoComplete="one-time-code"
          maxLength={6}
          required
        />
        <FormMessage state={state} />
        <SubmitButton pending={pending} pendingText="Checking…">
          Turn on
        </SubmitButton>
      </form>
    </div>
  );
}

function Manage({ status }: { status: TwoFactorStatus }) {
  const [codesState, codesAction, codesPending] = useActionState(newRecoveryCodes, undefined);
  const [offState, offAction, offPending] = useActionState(disableTwoFactor, undefined);
  return (
    <div className="flex flex-col gap-5">
      <p className="text-sm">
        <span className="font-semibold text-ok">On</span>
        {status.enabled_at &&
          ` since ${new Date(status.enabled_at).toLocaleDateString("en-GB", { timeZone: "Asia/Dhaka" })}`}
        . {status.recovery_codes_left} of 10 recovery codes left.
      </p>
      {codesState?.codes ? (
        <RecoveryCodes codes={codesState.codes} />
      ) : (
        <form action={codesAction} className="flex max-w-md flex-col gap-3">
          <p className="text-sm text-steel">
            New recovery codes replace the old ones. Confirm with a code from the app.
          </p>
          <Field label="Code from the app" name="code" type="text" inputMode="numeric" required />
          <FormMessage state={codesState} />
          <SubmitButton pending={codesPending} pendingText="Making…">
            Make new recovery codes
          </SubmitButton>
        </form>
      )}
      {status.required ? (
        <p className="text-sm text-steel">
          Your role must use two-factor sign-in, so it cannot be turned off here. If you lose your
          phone and your recovery codes, an admin can reset it.
        </p>
      ) : (
        <form action={offAction} className="flex max-w-md flex-col gap-3 border-t border-line pt-4">
          <p className="text-sm text-steel">Turning it off needs your password and a code.</p>
          <Field
            label="Password"
            name="password"
            type="password"
            autoComplete="current-password"
            required
          />
          <Field label="Code from the app" name="code" type="text" inputMode="numeric" required />
          <FormMessage state={offState} />
          <SubmitButton pending={offPending} pendingText="Turning off…">
            Turn off two-factor sign-in
          </SubmitButton>
        </form>
      )}
    </div>
  );
}

export function TwoFactorPanel({ status }: { status: TwoFactorStatus }) {
  return status.enabled ? <Manage status={status} /> : <SetUp />;
}
