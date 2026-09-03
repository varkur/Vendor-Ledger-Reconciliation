/**
 * Mapping Form Content — Column mapping interface for company or vendor ledger.
 * Extracted from MappingFormPage so the same form can be rendered either as a
 * full page (MappingFormPage) or inside a Dialog popup (e.g. right after a
 * direct-reconciliation upload).
 *
 * Shows:
 * - File header with row count
 * - Map Columns section (dropdown for each standard field → file header)
 * - Map Document Type section (file doc types → standard categories)
 * - A single Submit button to save and apply mapping
 */

import { useState, useRef, useEffect, useMemo } from 'react';
import { Button } from 'primereact/button';
import { Dropdown } from 'primereact/dropdown';
import { InputText } from 'primereact/inputtext';
import { RadioButton } from 'primereact/radiobutton';
import { Toast } from 'primereact/toast';
import { ProgressSpinner } from 'primereact/progressspinner';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@shared/services/apiClient';
import { useSelectedEntity } from '@shared/hooks/useSelectedEntity';

// Standard doc type categories
const DOC_TYPE_CATEGORIES = [
  { label: 'Invoice', value: 'Invoice' },
  { label: 'Payment', value: 'Payment' },
  { label: 'Debit Note', value: 'Debit Note' },
  { label: 'Credit Note', value: 'Credit Note' },
  { label: 'Journal', value: 'Journal' },
  { label: 'Adjusted', value: 'Adjusted' },
  { label: 'Receipt', value: 'Receipt' },
  { label: 'Knocking Off', value: 'Knocking Off' },
  { label: 'TDS Adjusted', value: 'TDS Adjusted' },
  { label: 'Opening Balance', value: 'Opening Balance' },
  { label: 'Closing Balance', value: 'Closing Balance' },
];

export interface MappingFormContentProps {
  caseId: string;
  side: 'company' | 'vendor';
  /** Called after the mapping has been saved and applied successfully. */
  onSubmitted: () => void;
  /** Optional label override for the Submit button (e.g. "Save & Continue"). */
  submitLabel?: string;
  /** Optional cancel handler — shows a Cancel button next to Submit when provided (used by popup mode). */
  onCancel?: () => void;
}

export const MappingFormContent = ({ caseId, side, onSubmitted, submitLabel, onCancel }: MappingFormContentProps) => {
  const toast = useRef<Toast>(null);
  const { companyCode } = useSelectedEntity();
  const queryClient = useQueryClient();
  const [isSaving, setIsSaving] = useState(false);

  // Column mapping state
  const [invoiceNo, setInvoiceNo] = useState('');
  const [invoiceDate, setInvoiceDate] = useState('');
  const [documentType, setDocumentType] = useState('');
  const [amountFormat, setAmountFormat] = useState<'single' | 'double'>('single');
  const [amountField, setAmountField] = useState('');
  const [debitField, setDebitField] = useState('');
  const [creditField, setCreditField] = useState('');
  const [partyCode, setPartyCode] = useState('');
  const [narration, setNarration] = useState('');
  const [clearingDocNumber, setClearingDocNumber] = useState('');
  const [clearingDate, setClearingDate] = useState('');
  const [tdsAmount, setTdsAmount] = useState('');
  const [postingDate, setPostingDate] = useState('');

  // Doc type mappings state
  const [docTypeMappings, setDocTypeMappings] = useState<Record<string, string>>({});

  // Fetch headers
  const { data: headersData, isLoading: headersLoading } = useQuery({
    queryKey: ['column-mapping-headers', caseId, side],
    queryFn: async () => {
      const { data } = await apiClient.get(`/vlr/column-mapping/${caseId}/headers`, {
        params: { side, company_code: companyCode },
      });
      return data as {
        headers: string[];
        sample_values: Record<string, string[]>;
        row_count: number;
        distinct_doc_types: string[];
        doc_type_summary: { doc_type: string; count: number; amount: number }[];
      };
    },
    enabled: !!caseId && !!side && !!companyCode,
  });

  // Fetch existing mapping
  const { data: existingMapping } = useQuery({
    queryKey: ['column-mapping', caseId, side],
    queryFn: async () => {
      const { data } = await apiClient.get(`/vlr/column-mapping/${caseId}`, {
        params: { side, company_code: companyCode },
      });
      return data;
    },
    enabled: !!caseId && !!side && !!companyCode,
  });

  // Fetch the case's vendor so we can auto-populate Party Code on BOTH sides —
  // the company ledger's "Party Code" is the vendor's code/PAN as it appears
  // on the company's books, same as the vendor ledger's self-reference.
  const { data: caseData } = useQuery({
    queryKey: ['case-for-mapping', caseId],
    queryFn: async () => {
      const { data } = await apiClient.get(`/vlr/cases/${caseId}`, {
        params: { company_code: companyCode },
      });
      return data;
    },
    enabled: !!caseId && !!companyCode,
  });

  const { data: vendorData } = useQuery({
    queryKey: ['vendor-for-mapping', caseData?.vendor_id],
    queryFn: async () => {
      const { data } = await apiClient.get(`/vlr/vendors/${caseData!.vendor_id}`, {
        params: { company_code: companyCode },
      });
      return data;
    },
    enabled: !!caseData?.vendor_id && !!companyCode,
  });

  // Vendor's PAN (auto-fills Party Code for both the company and vendor sides)
  const vendorPan = (vendorData as any)?.pan || (vendorData as any)?.vendor_code || '';

  // Some cases have legacy saved mappings where a field was accidentally
  // persisted as the raw dropdown option object (e.g. {label:"Select",
  // value:""}) instead of a plain string. Coerce anything non-string to ''
  // so the form (and the API on submit) never round-trips a bad shape.
  const asMappingString = (v: unknown): string => (typeof v === 'string' ? v : '');

  // Load existing mapping into state
  useEffect(() => {
    if (existingMapping?.mappings) {
      const m = existingMapping.mappings;
      setInvoiceNo(asMappingString(m.invoice_no));
      setInvoiceDate(asMappingString(m.invoice_date));
      setDocumentType(asMappingString(m.document_type));
      setAmountFormat(m.amount_format === 'double' ? 'double' : 'single');
      setAmountField(asMappingString(m.amount_field));
      setDebitField(asMappingString(m.debit_field));
      setCreditField(asMappingString(m.credit_field));
      setPartyCode(asMappingString(m.party_code));
      setNarration(asMappingString(m.narration));
      setClearingDocNumber(asMappingString(m.clearing_doc_number));
      setClearingDate(asMappingString(m.clearing_date));
      setTdsAmount(asMappingString(m.tds_amount));
      setPostingDate(asMappingString(m.posting_date));
    }
    if (existingMapping?.doc_type_mappings) {
      setDocTypeMappings(existingMapping.doc_type_mappings);
    }
  }, [existingMapping]);

  // Dropdown options from headers
  const headerOptions = useMemo(() => {
    if (!headersData?.headers) return [];
    return [
      { label: 'Select', value: '' },
      ...headersData.headers.map((h: string) => ({ label: h, value: h })),
    ];
  }, [headersData]);

  // Use distinct doc types returned by the backend
  const docTypes = useMemo(() => {
    return (headersData as any)?.distinct_doc_types || [];
  }, [headersData]);

  // Per-doc-type line item count and total amount (for the Count/Amount
  // columns on the Map Document Type table), keyed by doc type code.
  const docTypeSummaryByType = useMemo(() => {
    const map: Record<string, { count: number; amount: number }> = {};
    for (const row of headersData?.doc_type_summary || []) {
      map[row.doc_type] = { count: row.count, amount: row.amount };
    }
    return map;
  }, [headersData]);

  const docTypeTotals = useMemo(() => {
    return Object.values(docTypeSummaryByType).reduce(
      (acc, r) => ({ count: acc.count + r.count, amount: acc.amount + r.amount }),
      { count: 0, amount: 0 }
    );
  }, [docTypeSummaryByType]);

  const formatAmount = (n: number) =>
    n.toLocaleString('en-IN', { minimumFractionDigits: 0, maximumFractionDigits: 2 });

  const handleSubmit = async () => {
    if (!invoiceNo || !invoiceDate) {
      toast.current?.show({
        severity: 'warn',
        summary: 'Validation Error',
        detail: 'Invoice No and Invoice Date are required fields.',
        life: 5000,
      });
      return;
    }

    if (amountFormat === 'single' && !amountField) {
      toast.current?.show({
        severity: 'warn',
        summary: 'Validation Error',
        detail: 'Amount field is required for single column format.',
        life: 5000,
      });
      return;
    }

    if (amountFormat === 'double' && (!debitField || !creditField)) {
      toast.current?.show({
        severity: 'warn',
        summary: 'Validation Error',
        detail: 'Both Debit and Credit fields are required for double column format.',
        life: 5000,
      });
      return;
    }

    setIsSaving(true);
    try {
      // Save mapping
      await apiClient.post(`/vlr/column-mapping/${caseId}`, {
        side,
        mappings: {
          invoice_no: invoiceNo,
          invoice_date: invoiceDate,
          document_type: documentType,
          amount_format: amountFormat,
          amount_field: amountFormat === 'single' ? amountField : undefined,
          debit_field: amountFormat === 'double' ? debitField : undefined,
          credit_field: amountFormat === 'double' ? creditField : undefined,
          party_code: vendorPan ? `__fixed__:${vendorPan}` : (asMappingString(partyCode) || undefined),
          narration: asMappingString(narration) || undefined,
          clearing_doc_number: asMappingString(clearingDocNumber) || undefined,
          clearing_date: asMappingString(clearingDate) || undefined,
          tds_amount: asMappingString(tdsAmount) || undefined,
          posting_date: asMappingString(postingDate) || undefined,
        },
        doc_type_mappings: docTypeMappings,
      }, { params: { company_code: companyCode } });

      // Apply mapping
      await apiClient.post(`/vlr/column-mapping/${caseId}/apply`, {
        side,
      }, { params: { company_code: companyCode } });

      // Bug fix: this save/apply flow uses raw axios calls, not a React
      // Query mutation, so the ['column-mapping', caseId, side] query
      // (fetched above via useQuery, e.g. on first open when no mapping
      // existed yet and the response was `mappings: null`) never learns
      // the data changed. With the app-wide 5-minute staleTime, reopening
      // the Map Columns dialog afterward silently replayed that stale
      // (often empty) cached response instead of hitting the network —
      // "recheck mapping looks empty" even though the save succeeded and
      // the backend has the correct data. Invalidate both this query and
      // the headers query (doc-type summary can shift after a reupload)
      // so reopening always refetches the just-saved mapping.
      queryClient.invalidateQueries({ queryKey: ['column-mapping', caseId, side] });
      queryClient.invalidateQueries({ queryKey: ['column-mapping-headers', caseId, side] });

      toast.current?.show({
        severity: 'success',
        summary: 'Mapping Saved',
        detail: 'Column mapping has been saved and applied successfully.',
        life: 2000,
      });

      setTimeout(() => {
        onSubmitted();
      }, 800);
    } catch (error: any) {
      const detail = error.response?.data?.detail || 'Failed to save mapping.';
      toast.current?.show({
        severity: 'error',
        summary: 'Save Failed',
        detail,
        life: 8000,
      });
    } finally {
      setIsSaving(false);
    }
  };

  if (headersLoading) {
    return (
      <div className="flex justify-content-center align-items-center" style={{ minHeight: 300 }}>
        <ProgressSpinner style={{ width: '50px', height: '50px' }} />
      </div>
    );
  }

  return (
    <div>
      <Toast ref={toast} />

      {/* Info banner */}
      {headersData && (
        <div className="mb-3 text-sm" style={{ color: 'var(--color-text-muted)' }}>
          {headersData.row_count} entries found in file
        </div>
      )}

      {/* Map Columns Section */}
      <div className="em-card mb-4" style={{ padding: '24px' }}>
        <h4 className="mt-0" style={{ borderLeft: '3px solid #10b981', paddingLeft: '12px' }}>
          Map Columns
        </h4>

        <div className="flex flex-column gap-3">
          {/* Invoice No */}
          <div className="grid align-items-center">
            <div className="col-4"><label className="font-medium">Invoice No *</label></div>
            <div className="col-4">
              <Dropdown value={invoiceNo} options={headerOptions} onChange={e => setInvoiceNo(e.value)} className="w-full" placeholder="Select" />
            </div>
            <div className="col-4">
              {invoiceNo && headersData?.sample_values?.[invoiceNo] && (
                <div className="flex gap-2 flex-wrap">
                  {headersData.sample_values[invoiceNo].slice(0, 3).map((v: string, i: number) => (
                    <span key={i} className="text-xs p-1 px-2" style={{ background: '#f1f5f9', borderRadius: 4 }}>{v}</span>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Invoice Date */}
          <div className="grid align-items-center">
            <div className="col-4"><label className="font-medium">Invoice Date *</label></div>
            <div className="col-4">
              <Dropdown value={invoiceDate} options={headerOptions} onChange={e => setInvoiceDate(e.value)} className="w-full" placeholder="Select" />
            </div>
            <div className="col-4">
              {invoiceDate && headersData?.sample_values?.[invoiceDate] && (
                <div className="flex gap-2 flex-wrap">
                  {headersData.sample_values[invoiceDate].slice(0, 3).map((v: string, i: number) => (
                    <span key={i} className="text-xs p-1 px-2" style={{ background: '#f1f5f9', borderRadius: 4 }}>{v}</span>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Voucher / Document Type */}
          <div className="grid align-items-center">
            <div className="col-4"><label className="font-medium">Voucher / Document Type *</label></div>
            <div className="col-4">
              <Dropdown value={documentType} options={headerOptions} onChange={e => setDocumentType(e.value)} className="w-full" placeholder="Select" />
            </div>
            <div className="col-4">
              {documentType && headersData?.sample_values?.[documentType] && (
                <div className="flex gap-2 flex-wrap">
                  {headersData.sample_values[documentType].slice(0, 3).map((v: string, i: number) => (
                    <span key={i} className="text-xs p-1 px-2" style={{ background: '#f1f5f9', borderRadius: 4 }}>{v}</span>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Amount Format */}
          <div className="grid align-items-center">
            <div className="col-4"><label className="font-medium">Select Amount Format *</label></div>
            <div className="col-8">
              <div className="flex gap-4">
                <div className="flex align-items-center gap-2">
                  <RadioButton value="single" onChange={e => setAmountFormat(e.value)} checked={amountFormat === 'single'} />
                  <label>Single Column (Amount)</label>
                </div>
                <div className="flex align-items-center gap-2">
                  <RadioButton value="double" onChange={e => setAmountFormat(e.value)} checked={amountFormat === 'double'} />
                  <label>Double Column (Debit/Credit)</label>
                </div>
              </div>
            </div>
          </div>

          {/* Amount / Debit+Credit */}
          {amountFormat === 'single' ? (
            <div className="grid align-items-center">
              <div className="col-4"><label className="font-medium">Amount *</label></div>
              <div className="col-4">
                <Dropdown value={amountField} options={headerOptions} onChange={e => setAmountField(e.value)} className="w-full" placeholder="Select" />
              </div>
            </div>
          ) : (
            <>
              <div className="grid align-items-center">
                <div className="col-4"><label className="font-medium">Debit Amount *</label></div>
                <div className="col-4">
                  <Dropdown value={debitField} options={headerOptions} onChange={e => setDebitField(e.value)} className="w-full" placeholder="Select" />
                </div>
              </div>
              <div className="grid align-items-center">
                <div className="col-4"><label className="font-medium">Credit Amount *</label></div>
                <div className="col-4">
                  <Dropdown value={creditField} options={headerOptions} onChange={e => setCreditField(e.value)} className="w-full" placeholder="Select" />
                </div>
              </div>
            </>
          )}

          {/* Party Code */}
          <div className="grid align-items-center">
            <div className="col-4"><label className="font-medium">Party Code *</label></div>
            <div className="col-4">
              {vendorPan ? (
                <div className="flex align-items-center gap-2">
                  <InputText
                    value={vendorPan}
                    readOnly
                    className="w-full"
                    style={{ background: '#f8fafc' }}
                  />
                  <i className="pi pi-check-circle" style={{ color: '#10b981' }} title="Auto-filled from vendor PAN" />
                </div>
              ) : (
                <Dropdown value={partyCode} options={headerOptions} onChange={e => setPartyCode(e.value)} className="w-full" placeholder="Select" />
              )}
            </div>
            {vendorPan && (
              <div className="col-4">
                <small style={{ color: 'var(--color-text-muted)' }}>Auto-filled from vendor master (PAN)</small>
              </div>
            )}
          </div>

          {/* Narration (optional) */}
          <div className="grid align-items-center">
            <div className="col-4"><label>Narration (optional)</label></div>
            <div className="col-4">
              <Dropdown value={narration} options={headerOptions} onChange={e => setNarration(e.value)} className="w-full" placeholder="Select" />
            </div>
          </div>

          {/* Clearing Document Number (optional) */}
          <div className="grid align-items-center">
            <div className="col-4"><label>Clearing Document Number (optional)</label></div>
            <div className="col-4">
              <Dropdown value={clearingDocNumber} options={headerOptions} onChange={e => setClearingDocNumber(e.value)} className="w-full" placeholder="Select" />
            </div>
          </div>

          {/* Clearing Date (optional) */}
          <div className="grid align-items-center">
            <div className="col-4"><label>Clearing Date (optional)</label></div>
            <div className="col-4">
              <Dropdown value={clearingDate} options={headerOptions} onChange={e => setClearingDate(e.value)} className="w-full" placeholder="Select" />
            </div>
          </div>

          {/* TDS Amount (optional) */}
          <div className="grid align-items-center">
            <div className="col-4"><label>TDS Amount (optional)</label></div>
            <div className="col-4">
              <Dropdown value={tdsAmount} options={headerOptions} onChange={e => setTdsAmount(e.value)} className="w-full" placeholder="Select" />
            </div>
          </div>

          {/* Posting Date (optional) */}
          <div className="grid align-items-center">
            <div className="col-4"><label>Posting Date (optional)</label></div>
            <div className="col-4">
              <Dropdown value={postingDate} options={headerOptions} onChange={e => setPostingDate(e.value)} className="w-full" placeholder="Select" />
            </div>
          </div>
        </div>
      </div>

      {/* Map Document Type Section */}
      {docTypes.length > 0 && (
        <div className="em-card mb-4" style={{ padding: '24px' }}>
          <h4 className="mt-0" style={{ borderLeft: '3px solid #10b981', paddingLeft: '12px' }}>
            Map Document Type
          </h4>

          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--surface-border)' }}>
                <th style={{ padding: '10px', textAlign: 'left', fontWeight: 600 }}>File Doc Type</th>
                <th style={{ padding: '10px', textAlign: 'left', fontWeight: 600 }}>Doctype Description</th>
                <th style={{ padding: '10px', textAlign: 'center', fontWeight: 600 }}>Status</th>
                <th style={{ padding: '10px', textAlign: 'right', fontWeight: 600 }}>Count</th>
                <th style={{ padding: '10px', textAlign: 'right', fontWeight: 600 }}>Amount</th>
              </tr>
            </thead>
            <tbody>
              {docTypes.map((dt: string) => {
                const summary = docTypeSummaryByType[dt];
                return (
                  <tr key={dt} style={{ borderBottom: '1px solid var(--surface-border)' }}>
                    <td style={{ padding: '10px' }}>{dt}</td>
                    <td style={{ padding: '10px' }}>
                      <Dropdown
                        value={docTypeMappings[dt] || ''}
                        options={DOC_TYPE_CATEGORIES}
                        onChange={e => setDocTypeMappings(prev => ({ ...prev, [dt]: e.value }))}
                        placeholder="Select"
                        style={{ width: '200px' }}
                      />
                    </td>
                    <td style={{ padding: '10px', textAlign: 'center' }}>
                      {docTypeMappings[dt] ? (
                        <i className="pi pi-check-circle" style={{ color: '#10b981' }} />
                      ) : (
                        <i className="pi pi-times-circle" style={{ color: '#ef4444' }} />
                      )}
                    </td>
                    <td style={{ padding: '10px', textAlign: 'right' }}>{summary?.count ?? 0}</td>
                    <td style={{ padding: '10px', textAlign: 'right' }}>
                      {summary ? formatAmount(summary.amount) : '0'}
                    </td>
                  </tr>
                );
              })}
            </tbody>
            <tfoot>
              <tr style={{ borderTop: '2px solid var(--surface-border)', fontWeight: 600 }}>
                <td style={{ padding: '10px' }} colSpan={3}>Total</td>
                <td style={{ padding: '10px', textAlign: 'right' }}>{docTypeTotals.count}</td>
                <td style={{ padding: '10px', textAlign: 'right' }}>{formatAmount(docTypeTotals.amount)}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}

      {/* Single Submit action */}
      <div className="flex justify-content-end gap-2">
        {onCancel && (
          <Button
            label="Cancel"
            className="p-button-outlined p-button-secondary"
            disabled={isSaving}
            onClick={onCancel}
          />
        )}
        <Button
          label={submitLabel || 'Submit'}
          icon="pi pi-check"
          onClick={handleSubmit}
          loading={isSaving}
        />
      </div>
    </div>
  );
};
