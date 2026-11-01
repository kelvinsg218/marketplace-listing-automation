"use client";

import Link from "next/link";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { Alert, Button, Field, Input } from "@/components/ui";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api("/auth/password-reset/request", { method: "POST", body: { email } });
      setSent(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Falha ao enviar.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <h2 className="text-2xl font-bold tracking-tight">Recuperar senha</h2>
      <p className="mt-1 mb-8 text-sm text-muted">Enviaremos um link para criar uma nova senha.</p>
      {sent ? (
        <Alert tone="ok">Se o e-mail estiver cadastrado, você receberá as instruções em instantes. O link vale por 30 minutos.</Alert>
      ) : (
        <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
          {error && <Alert>{error}</Alert>}
          <Field label="E-mail">{(id) => <Input id={id} type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />}</Field>
          <Button type="submit" variant="primary" busy={busy} className="w-full">Enviar link</Button>
        </form>
      )}
      <p className="mt-8 text-sm text-center"><Link href="/entrar/" className="text-muted hover:text-accent">Voltar para o login</Link></p>
    </>
  );
}
