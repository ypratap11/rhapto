"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError, apiClient, getSettings, setSettings, unwrap } from "@/lib/api/client";

export default function SettingsPage() {
  const queryClient = useQueryClient();
  const apiUrlRef = useRef<HTMLInputElement>(null);
  const tokenRef = useRef<HTMLInputElement>(null);
  const [show, setShow] = useState(false);
  const [testing, setTesting] = useState(false);

  // Read the stored settings straight into the (uncontrolled) inputs. This
  // touches the DOM directly rather than React state, so it stays a plain
  // effect side-effect instead of a state sync and avoids any server/client
  // mismatch for the input values (the server never sees localStorage).
  useEffect(() => {
    const s = getSettings();
    if (apiUrlRef.current) apiUrlRef.current.value = s.apiUrl;
    if (tokenRef.current) tokenRef.current.value = s.token;
  }, []);

  function readForm() {
    return { apiUrl: apiUrlRef.current?.value ?? "", token: tokenRef.current?.value ?? "" };
  }

  function save() {
    setSettings(readForm());
    void queryClient.invalidateQueries();
    toast.success("Settings saved");
  }

  async function test() {
    setSettings(readForm());
    setTesting(true);
    try {
      const me = await unwrap(apiClient().GET("/api/v1/me"));
      toast.success(`Connected as ${me.email}`);
    } catch (error) {
      toast.error(error instanceof ApiError ? `${error.status}: ${error.message}` : "Could not reach the API");
    } finally {
      setTesting(false);
    }
  }

  return (
    <div className="mx-auto max-w-xl space-y-6">
      <h1 className="text-2xl">Settings</h1>
      <Card>
        <CardHeader>
          <CardTitle>API connection</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-1">
            <Label htmlFor="apiUrl">API URL</Label>
            <Input id="apiUrl" ref={apiUrlRef} defaultValue="" placeholder="http://localhost:8000" />
          </div>
          <div className="space-y-1">
            <Label htmlFor="token">Bearer token</Label>
            <div className="flex gap-2">
              <Input id="token" ref={tokenRef} type={show ? "text" : "password"} defaultValue="" autoComplete="off" />
              <Button type="button" variant="outline" onClick={() => setShow((v) => !v)} aria-pressed={show}>
                {show ? "Hide" : "Show"}
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">Stored only in this browser. It is the RHAPTO_API_TOKEN from your .env.</p>
          </div>
          <div className="flex gap-2">
            <Button onClick={save}>Save</Button>
            <Button variant="outline" onClick={test} disabled={testing}>
              {testing ? "Testing…" : "Test connection"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
