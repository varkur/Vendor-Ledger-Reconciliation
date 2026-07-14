/**
 * Email Configuration page — SMTP settings for outbound emails.
 * Fields: SMTP Host, Port, Username, Password, Sender Email, Sender Name, TLS toggle.
 * Actions: Save, Test Connection.
 */

import { useState, useRef, useEffect } from 'react';
import { InputText } from 'primereact/inputtext';
import { InputNumber } from 'primereact/inputnumber';
import { Password } from 'primereact/password';
import { InputSwitch } from 'primereact/inputswitch';
import { Button } from 'primereact/button';
import { Toast } from 'primereact/toast';
import { ProgressSpinner } from 'primereact/progressspinner';
import { Message } from 'primereact/message';
import { apiClient } from '@shared/services/apiClient';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useSelectedEntity } from '@shared/hooks/useSelectedEntity';

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

interface EmailConfig {
  smtp_host: string;
  smtp_port: number;
  smtp_username: string;
  smtp_password: string;
  sender_email: string;
  sender_name: string;
  use_tls: boolean;
  is_configured: boolean;
}

interface TestEmailResponse {
  success: boolean;
  message: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// API
// ─────────────────────────────────────────────────────────────────────────────

const EMAIL_CONFIG_KEY = 'email-config';

async function getEmailConfig(companyCode: string): Promise<EmailConfig> {
  const { data } = await apiClient.get<EmailConfig>('/vlr/settings/email-config', {
    params: { company_code: companyCode },
  });
  return data;
}

async function updateEmailConfig(config: Partial<EmailConfig>, companyCode: string): Promise<EmailConfig> {
  const { data } = await apiClient.put<EmailConfig>('/vlr/settings/email-config', config, {
    params: { company_code: companyCode },
  });
  return data;
}

async function testEmailConnection(companyCode: string): Promise<TestEmailResponse> {
  const { data } = await apiClient.post<TestEmailResponse>('/vlr/settings/email-config/test', null, {
    params: { company_code: companyCode },
  });
  return data;
}

// ─────────────────────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────────────────────

export const EmailConfigPage = () => {
  const toast = useRef<Toast>(null);
  const queryClient = useQueryClient();
  const { companyCode } = useSelectedEntity();

  // Form state
  const [smtpHost, setSmtpHost] = useState('');
  const [smtpPort, setSmtpPort] = useState<number | null>(587);
  const [smtpUsername, setSmtpUsername] = useState('');
  const [smtpPassword, setSmtpPassword] = useState('');
  const [senderEmail, setSenderEmail] = useState('');
  const [senderName, setSenderName] = useState('');
  const [useTls, setUseTls] = useState(true);

  // Query
  const { data: config, isLoading, isError, error, refetch } = useQuery<EmailConfig, Error>({
    queryKey: [EMAIL_CONFIG_KEY, companyCode],
    queryFn: () => getEmailConfig(companyCode),
    enabled: !!companyCode,
    retry: 2,
    staleTime: 5 * 60 * 1000,
  });

  // Sync form when data loads
  useEffect(() => {
    if (config) {
      setSmtpHost(config.smtp_host);
      setSmtpPort(config.smtp_port);
      setSmtpUsername(config.smtp_username);
      setSenderEmail(config.sender_email);
      setSenderName(config.sender_name);
      setUseTls(config.use_tls);
      // Don't set password from server (masked)
    }
  }, [config]);

  // Save mutation
  const saveMutation = useMutation<EmailConfig, Error, Partial<EmailConfig>>({
    mutationFn: (data) => updateEmailConfig(data, companyCode),
    onSuccess: (data) => {
      queryClient.setQueryData([EMAIL_CONFIG_KEY, companyCode], data);
      toast.current?.show({
        severity: 'success',
        summary: 'Saved',
        detail: 'Email configuration updated successfully.',
      });
    },
    onError: (err) => {
      toast.current?.show({
        severity: 'error',
        summary: 'Save Failed',
        detail: err.message || 'Failed to save email configuration.',
      });
    },
  });

  // Test connection mutation
  const testMutation = useMutation<TestEmailResponse, Error>({
    mutationFn: () => testEmailConnection(companyCode),
    onSuccess: (res) => {
      toast.current?.show({
        severity: res.success ? 'success' : 'warn',
        summary: res.success ? 'Connection OK' : 'Connection Failed',
        detail: res.message,
      });
    },
    onError: (err) => {
      toast.current?.show({
        severity: 'error',
        summary: 'Test Failed',
        detail: err.message || 'Could not test email connection.',
      });
    },
  });

  const handleSave = () => {
    saveMutation.mutate({
      smtp_host: smtpHost,
      smtp_port: smtpPort ?? 587,
      smtp_username: smtpUsername,
      ...(smtpPassword ? { smtp_password: smtpPassword } : {}),
      sender_email: senderEmail,
      sender_name: senderName,
      use_tls: useTls,
    });
  };

  if (isLoading) {
    return (
      <div className="flex justify-content-center align-items-center" style={{ minHeight: 300 }}>
        <ProgressSpinner style={{ width: '50px', height: '50px' }} />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex flex-column align-items-center gap-3" style={{ padding: '2rem' }}>
        <Message severity="error" text={error?.message || 'Failed to load email configuration.'} />
        <Button label="Retry" icon="pi pi-refresh" onClick={() => refetch()} />
      </div>
    );
  }

  return (
    <div>
      <Toast ref={toast} />

      <div className="em-page-header">
        <h2>Email Configuration</h2>
      </div>

      <div className="em-card" style={{ maxWidth: 700 }}>
        <div className="flex flex-column gap-4">
          {/* SMTP Host */}
          <div>
            <label htmlFor="smtp-host" className="font-bold text-sm block mb-1">
              SMTP Host *
            </label>
            <InputText
              id="smtp-host"
              value={smtpHost}
              onChange={(e) => setSmtpHost(e.target.value)}
              placeholder="smtp.gmail.com"
              className="w-full"
            />
          </div>

          {/* SMTP Port */}
          <div>
            <label htmlFor="smtp-port" className="font-bold text-sm block mb-1">
              SMTP Port *
            </label>
            <InputNumber
              id="smtp-port"
              value={smtpPort}
              onValueChange={(e) => setSmtpPort(e.value ?? null)}
              placeholder="587"
              className="w-full"
              min={1}
              max={65535}
              useGrouping={false}
            />
          </div>

          {/* Username */}
          <div>
            <label htmlFor="smtp-username" className="font-bold text-sm block mb-1">
              Username
            </label>
            <InputText
              id="smtp-username"
              value={smtpUsername}
              onChange={(e) => setSmtpUsername(e.target.value)}
              placeholder="your-email@company.com"
              className="w-full"
            />
          </div>

          {/* Password */}
          <div>
            <label htmlFor="smtp-password" className="font-bold text-sm block mb-1">
              Password
            </label>
            <Password
              id="smtp-password"
              value={smtpPassword}
              onChange={(e) => setSmtpPassword(e.target.value)}
              placeholder="••••••••"
              className="w-full"
              toggleMask
              feedback={false}
            />
          </div>

          {/* Sender Email */}
          <div>
            <label htmlFor="sender-email" className="font-bold text-sm block mb-1">
              Sender Email *
            </label>
            <InputText
              id="sender-email"
              value={senderEmail}
              onChange={(e) => setSenderEmail(e.target.value)}
              placeholder="noreply@company.com"
              className="w-full"
            />
          </div>

          {/* Sender Name */}
          <div>
            <label htmlFor="sender-name" className="font-bold text-sm block mb-1">
              Sender Name
            </label>
            <InputText
              id="sender-name"
              value={senderName}
              onChange={(e) => setSenderName(e.target.value)}
              placeholder="Emcure VLR System"
              className="w-full"
            />
          </div>

          {/* TLS Toggle */}
          <div className="flex align-items-center gap-2">
            <InputSwitch checked={useTls} onChange={(e) => setUseTls(e.value)} />
            <label className="font-bold text-sm">Use TLS/SSL</label>
          </div>

          {/* Actions */}
          <div className="flex justify-content-end gap-2 pt-3 border-top-1 surface-border">
            <Button
              label="Test Connection"
              icon="pi pi-bolt"
              className="p-button-outlined"
              onClick={() => testMutation.mutate()}
              loading={testMutation.isPending}
            />
            <Button
              label="Save"
              icon="pi pi-save"
              onClick={handleSave}
              loading={saveMutation.isPending}
            />
          </div>
        </div>
      </div>
    </div>
  );
};
