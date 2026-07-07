/**
 * Vendor Portal Upload page — Allows vendors to upload their statement files.
 * Includes file upload with counter showing uploaded files.
 */

import { useState, useRef } from 'react';
import { FileUpload, FileUploadHandlerEvent } from 'primereact/fileupload';
import { DataTable } from 'primereact/datatable';
import { Column } from 'primereact/column';
import { Tag } from 'primereact/tag';
import { Toast } from 'primereact/toast';

interface UploadedFile {
  id: string;
  fileName: string;
  fileSize: string;
  uploadDate: string;
  status: 'Processing' | 'Processed' | 'Error';
}

export const PortalUploadPage = () => {
  const toast = useRef<Toast>(null);
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([
    { id: '1', fileName: 'Ledger_Statement_Apr2025_Mar2026.xlsx', fileSize: '245 KB', uploadDate: '01-Jul-26 10:15 AM', status: 'Processed' },
    { id: '2', fileName: 'Invoice_Details_Q4.pdf', fileSize: '1.2 MB', uploadDate: '01-Jul-26 10:16 AM', status: 'Processed' },
  ]);

  const handleUpload = (event: FileUploadHandlerEvent) => {
    const files = event.files;
    const newFiles: UploadedFile[] = files.map((file, idx) => ({
      id: String(uploadedFiles.length + idx + 1),
      fileName: file.name,
      fileSize: `${(file.size / 1024).toFixed(0)} KB`,
      uploadDate: new Date().toLocaleString('en-IN', { day: '2-digit', month: 'short', year: '2-digit', hour: '2-digit', minute: '2-digit' }),
      status: 'Processing' as const,
    }));

    setUploadedFiles((prev) => [...prev, ...newFiles]);
    toast.current?.show({ severity: 'success', summary: 'Upload Complete', detail: `${files.length} file(s) uploaded successfully.` });

    // Simulate processing
    setTimeout(() => {
      setUploadedFiles((prev) =>
        prev.map((f) => (f.status === 'Processing' ? { ...f, status: 'Processed' } : f))
      );
    }, 3000);
  };

  const statusTemplate = (rowData: UploadedFile) => {
    const severityMap: Record<string, 'success' | 'warning' | 'danger'> = {
      Processed: 'success',
      Processing: 'warning',
      Error: 'danger',
    };
    return <Tag value={rowData.status} severity={severityMap[rowData.status]} />;
  };

  return (
    <div style={{ maxWidth: 900, margin: '0 auto', padding: '24px' }}>
      <Toast ref={toast} />

      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <h2 style={{ margin: 0 }}>Upload Statement</h2>
        <p style={{ color: 'var(--color-text-muted)', margin: '4px 0 0' }}>
          Upload your ledger statement for reconciliation. Supported formats: Excel (.xlsx, .xls), PDF, CSV.
        </p>
      </div>

      {/* Upload Counter */}
      <div className="em-card mb-3">
        <div className="flex align-items-center justify-content-between">
          <div>
            <span style={{ fontSize: '1.25rem', fontWeight: 600 }}>{uploadedFiles.length}</span>
            <span style={{ color: 'var(--color-text-muted)', marginLeft: 8 }}>file(s) uploaded</span>
          </div>
          <div className="flex gap-2">
            <Tag value={`${uploadedFiles.filter((f) => f.status === 'Processed').length} Processed`} severity="success" />
            <Tag value={`${uploadedFiles.filter((f) => f.status === 'Processing').length} Processing`} severity="warning" />
          </div>
        </div>
      </div>

      {/* File Upload */}
      <div className="em-card mb-3">
        <FileUpload
          name="vendorStatement"
          customUpload
          uploadHandler={handleUpload}
          multiple
          accept=".xlsx,.xls,.csv,.pdf"
          maxFileSize={10000000}
          emptyTemplate={
            <div className="flex flex-column align-items-center p-4">
              <i className="pi pi-cloud-upload" style={{ fontSize: '3rem', color: 'var(--color-text-muted)' }} />
              <p style={{ color: 'var(--color-text-muted)', margin: '12px 0 0' }}>
                Drag and drop files here, or click to browse
              </p>
              <p style={{ fontSize: '0.8rem', color: 'var(--color-text-muted)' }}>
                Max file size: 10MB | Supported: .xlsx, .xls, .csv, .pdf
              </p>
            </div>
          }
          chooseLabel="Browse Files"
          uploadLabel="Upload"
          cancelLabel="Clear"
        />
      </div>

      {/* Uploaded Files Table */}
      {uploadedFiles.length > 0 && (
        <div className="em-card" style={{ padding: 0 }}>
          <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--color-border, #e5e7eb)' }}>
            <h3 style={{ margin: 0, fontSize: '1rem' }}>Uploaded Files</h3>
          </div>
          <DataTable value={uploadedFiles} emptyMessage="No files uploaded.">
            <Column field="fileName" header="File Name" style={{ width: '40%' }} />
            <Column field="fileSize" header="Size" style={{ width: '12%' }} />
            <Column field="uploadDate" header="Upload Date" style={{ width: '25%' }} />
            <Column header="Status" body={statusTemplate} style={{ width: '15%' }} />
          </DataTable>
        </div>
      )}
    </div>
  );
};
