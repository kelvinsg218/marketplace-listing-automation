"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { Alert, Button, Field, Input } from "@/components/ui";

export default function ResetPasswordPage() {
  const [token, setToken] = useState<string | null | undefined>(undefined); // undefined = not read yet
  const [password, setPassword] = useState("");
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    // The token travels in the URL fragment, which is never sent to the server; drop it from the address bar.
    const t = new URLSearchParams(window.location.hash.slice(1)).get("token");
    setToken(t);
    if (t) history.replaceState(null, "", window.location.pathname);
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api("/auth/password-reset/confirm", { method: "POST", body: { token, password } });
      setDone(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Falha ao redefinir.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <h2 className="text-2xl font-bold tracking-tight">Nova senha</h2>
      <p className="mt-1 mb-8 text-sm text-muted">Ao salvar, todas as sessões abertas da conta são encerradas.</p>
      {done ? (
        <Alert tone="ok">Senha alterada. <Link href="/entrar/" className="underline">Entrar com a nova senha</Link>.</Alert>
      ) : token === undefined ? null : token === null ? (
        <Alert>Link inválido. Peça um novo em <Link href="/recuperar-senha/" className="underline">Recuperar senha</Link>.</Alert>
      ) : (
        <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
          {error && <Alert>{error}</Alert>}
          <Field label="Nova senha" hint="Pelo menos 10 caracteres.">{(id, d) => (
            <Input id={id} type="password" autoComplete="new-password" aria-describedby={d} value={password} onChange={(e) => setPassword(e.target.value)} />
          )}</Field>
          <Button type="submit" variant="primary" busy={busy} className="w-full">Salvar nova senha</Button>
        </form>
      )}
    </>
  );
}
