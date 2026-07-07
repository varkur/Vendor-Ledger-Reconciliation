/**
 * Import Parties Dialog — upload CSV/Excel file for bulk vendor import.
 */

import { useState, useRef, useEffect } from 'react';
import { Dialog } from 'primereact/dialog';
import { Button } from 'primereact/button';
import { Message } from 'primereact/message';
import { ProgressBar } from 'primereact/progressbar';
import { useBulkImportVendors } from '../hooks/useVendors';
import { BulkImportResponse } from '../api/vendorApi';

const DEFAULT_COMPANY_CODE = '1000';

interface ImportDialogProps {
  visible: boolean;
  onHide: () => void;
}

export const ImportDialog = ({ visible, onHide }: ImportDialogProps) => {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [importResult, setImportResult] = useState<BulkImportResponse | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const bulkImport = useBulkImportVendors();

  useEffect(() => {
    if (!visible) {
      setSelectedFile(null);
      setImportResult(null);
    }
  }, [visible]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setSelectedFile(file);
      setImportResult(null);
    }
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0];
    if (file) {
      const ext = file.name.split('.').pop()?.toLowerCase();
      if (ext === 'csv' || ext === 'xlsx' || ext === 'xls') {
        setSelectedFile(file);
        setImportResult(null);
      }
    }
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
  };

  const handleImport = () => {
    if (!selectedFile) return;

    bulkImport.mutate(
      { file: selectedFile, companyCode: DEFAULT_COMPANY_CODE },
      {
        onSuccess: (data) => {
          setImportResult(data);
        },
      }
    );
  };

  const handleBrowse = () => {
    fileInputRef.current?.click();
  };

  const dialogFooter = (
    <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem' }}>
      <Button
        label="Cancel"
        icon="pi pi-times"
        className="p-button-text"
        onClick={onHide}
        disabled={bulkImport.isPending}
      />
      {!importResult && (
        <Button
          label="Import"
          icon="pi pi-upload"
          onClick={handleImport}
          disabled={!selectedFile || bulkImport.isPending}
          loading={bulkImport.isPending}
        />
      )}
      {importResult && (
        <Button label="Done" icon="pi pi-check" onClick={onHide} />
      )}
    </div>
  );

  return (
    <Dialog
      header="Import Parties"
      visible={visible}
      onHide={onHide}
      style={{ width: '500px' }}
      footer={dialogFooter}
      modal
      closable
      draggable={false}
    >
      {/* Instructions */}
      <p style={{ margin: '0 0 1rem', color: 'var(--text-color-secondary)' }}>
        Upload a CSV/Excel file with party data matching the template format.
      </p>

      {/* File Drop Zone */}
      {!importResult && (
        <>
          <input
            type="file"
            ref={fileInputRef}
            style={{ display: 'none' }}
            accept=".csv,.xlsx,.xls"
            onChange={handleFileChange}
          />
          <div
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onClick={handleBrowse}
            style={{
              border: '2px dashed var(--surface-border)',
              borderRadius: 'var(--border-radius)',
              padding: '2rem',
              textAlign: 'center',
              cursor: 'pointer',
              backgroundColor: 'var(--surface-ground)',
              transition: 'border-color 0.2s',
            }}
          >
            <i
              className="pi pi-cloud-upload"
              style={{ fontSize: '2rem', color: 'var(--primary-color)', marginBottom: '0.5rem', display: 'block' }}
            />
            {selectedFile ? (
              <div>
                <p style={{ margin: 0, fontWeight: 500 }}>{selectedFile.name}</p>
                <small style={{ color: 'var(--text-color-secondary)' }}>
                  {(selectedFile.size / 1024).toFixed(1)} KB
                </small>
              </div>
            ) : (
              <div>
                <p style={{ margin: 0 }}>
                  Drag & drop a file here, or <span style={{ color: 'var(--primary-color)', fontWeight: 500 }}>browse</span>
                </p>
                <small style={{ color: 'var(--text-color-secondary)' }}>
                  Accepted formats: .csv, .xlsx, .xls
                </small>
              </div>
            )}
          </div>
        </>
      )}

      {/* Loading state */}
      {bulkImport.isPending && (
        <div style={{ marginTop: '1rem' }}>
          <ProgressBar mode="indeterminate" style={{ height: '6px' }} />
          <small style={{ color: 'var(--text-color-secondary)' }}>Importing parties...</small>
        </div>
      )}

      {/* Success result */}
      {importResult && (
        <div style={{ marginTop: '1rem' }}>
          <Message
            severity={importResult.errors > 0 ? 'warn' : 'success'}
            style={{ width: '100%', marginBottom: '0.5rem' }}
            text={`Import complete: ${importResult.imported} imported, ${importResult.errors} failed.`}
          />
          {importResult.details && importResult.details.length > 0 && (
            <div
              style={{
                maxHeight: '150px',
                overflow: 'auto',
                padding: '0.5rem',
                backgroundColor: 'var(--surface-ground)',
                borderRadius: 'var(--border-radius)',
                fontSize: '0.85rem',
              }}
            >
              {importResult.details.map((detail, idx) => (
                <div key={idx} style={{ marginBottom: '0.25rem', color: 'var(--text-color-secondary)' }}>
                  • {detail}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Error state */}
      {bulkImport.isError && !importResult && (
        <div style={{ marginTop: '1rem' }}>
          <Message
            severity="error"
            style={{ width: '100%' }}
            text={
              bulkImport.error instanceof Error
                ? bulkImport.error.message
                : 'Import failed. Please check your file and try again.'
            }
          />
        </div>
      )}
    </Dialog>
  );
};
