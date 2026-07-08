/**
 * ColumnMappingPanel — Main component for the column mapping flow.
 *
 * Orchestrates:
 * 1. File upload (PrimeReact FileUpload)
 * 2. 10-row data preview (PrimeReact DataTable)
 * 3. Per-column dropdown tag assignment (PrimeReact Dropdown)
 * 4. Auto-mapping suggestions with confidence badges (High/Medium/Low)
 * 5. Template save/load functionality
 *
 * Requirements: 9.1, 9.2, 9.3, 10.1, 10.2, 10.3, 11.1, 11.2, 11.3, 11.4
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Badge } from 'primereact/badge';
import { Button } from 'primereact/button';
import { Column } from 'primereact/column';
import { DataTable } from 'primereact/datatable';
import { Dropdown } from 'primereact/dropdown';
import { FileUpload, type FileUploadSelectEvent } from 'primereact/fileupload';
import { Message } from 'primereact/message';
import { ProgressSpinner } from 'primereact/progressspinner';
import { Tag } from 'primereact/tag';

import {
  TRANSACTION_TYPE_TAGS,
  type ColumnMappingEntry,
  type ColumnSuggestion,
  type ConfidenceLevel,
  type TransactionTypeTag,
} from './columnMappingApi';
import {
  useAutoMap,
  useGetTemplate,
  usePreviewFile,
  useSaveTemplate,
} from './useColumnMapping';

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

export interface ColumnMappingPanelProps {
  /** Vendor ID for template save/load. */
  vendorId?: string;
  /** Callback when mapping is confirmed. */
  onMappingConfirmed?: (mappings: ColumnMappingEntry[]) => void;
}

interface ColumnAssignment {
  columnIndex: number;
  header: string;
  tag: TransactionTypeTag | null;
  suggestion: ColumnSuggestion | null;
}

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

/** Map confidence level to PrimeReact severity for visual styling. */
function getConfidenceSeverity(
  confidence: ConfidenceLevel | null
): 'success' | 'warning' | 'secondary' | 'info' {
  switch (confidence) {
    case 'High':
      return 'success';
    case 'Medium':
      return 'warning';
    case 'Low':
      return 'secondary';
    default:
      return 'info';
  }
}

/** Dropdown options for tag assignment. */
const TAG_OPTIONS = TRANSACTION_TYPE_TAGS.map((tag) => ({
  label: tag.replace(/_/g, ' '),
  value: tag,
}));

// ─────────────────────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────────────────────

export const ColumnMappingPanel = ({
  vendorId,
  onMappingConfirmed,
}: ColumnMappingPanelProps) => {
  // ─── State ───────────────────────────────────────────────────────────────────
  const [assignments, setAssignments] = useState<ColumnAssignment[]>([]);
  const [previewHeaders, setPreviewHeaders] = useState<string[]>([]);
  const [previewRows, setPreviewRows] = useState<string[][]>([]);
  const [filename, setFilename] = useState<string>('');
  const [totalRowCount, setTotalRowCount] = useState(0);
  const [templateApplied, setTemplateApplied] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);

  // ─── API Hooks ───────────────────────────────────────────────────────────────
  const previewMutation = usePreviewFile();
  const autoMapMutation = useAutoMap();
  const saveTemplateMutation = useSaveTemplate();
  const templateQuery = useGetTemplate(vendorId);

  // ─── Derived state ───────────────────────────────────────────────────────────
  const hasPreview = previewHeaders.length > 0;
  const isLoading = previewMutation.isPending || autoMapMutation.isPending;

  // Convert preview rows into DataTable-compatible objects
  const tableData = useMemo(() => {
    return previewRows.map((row, rowIdx) => {
      const rowObj: Record<string, string> = { _rowIndex: String(rowIdx) };
      previewHeaders.forEach((_header, colIdx) => {
        rowObj[`col_${colIdx}`] = row[colIdx] ?? '';
      });
      return rowObj;
    });
  }, [previewRows, previewHeaders]);

  // ─── Apply template when loaded ─────────────────────────────────────────────
  useEffect(() => {
    if (
      templateQuery.data &&
      hasPreview &&
      !templateApplied &&
      assignments.length > 0
    ) {
      const templateMappings = templateQuery.data.mappings;
      setAssignments((prev) =>
        prev.map((a) => {
          const templateEntry = templateMappings.find(
            (m) => m.column_index === a.columnIndex
          );
          if (templateEntry) {
            return { ...a, tag: templateEntry.tag as TransactionTypeTag };
          }
          return a;
        })
      );
      setTemplateApplied(true);
    }
  }, [templateQuery.data, hasPreview, templateApplied, assignments.length]);

  // ─── Handlers ────────────────────────────────────────────────────────────────

  const handleFileSelect = useCallback(
    async (event: FileUploadSelectEvent) => {
      const file = event.files[0];
      if (!file) return;

      // Reset state
      setSaveSuccess(false);
      setTemplateApplied(false);

      previewMutation.mutate(file, {
        onSuccess: (data) => {
          setPreviewHeaders(data.headers);
          setPreviewRows(data.rows);
          setFilename(data.filename);
          setTotalRowCount(data.total_row_count);

          // Initialize assignments with empty tags
          const initialAssignments: ColumnAssignment[] = data.headers.map(
            (header, idx) => ({
              columnIndex: idx,
              header,
              tag: null,
              suggestion: null,
            })
          );
          setAssignments(initialAssignments);

          // Trigger auto-mapping
          autoMapMutation.mutate(data.headers, {
            onSuccess: (autoMapData) => {
              setAssignments((prev) =>
                prev.map((a) => {
                  const suggestion = autoMapData.suggestions.find(
                    (s) => s.column_index === a.columnIndex
                  );
                  if (suggestion) {
                    return {
                      ...a,
                      suggestion,
                      // Pre-select only high confidence suggestions
                      tag: suggestion.should_preselect
                        ? (suggestion.suggested_tag as TransactionTypeTag)
                        : a.tag,
                    };
                  }
                  return a;
                })
              );
            },
          });
        },
      });
    },
    [previewMutation, autoMapMutation]
  );

  const handleTagChange = useCallback(
    (columnIndex: number, newTag: TransactionTypeTag | null) => {
      setAssignments((prev) =>
        prev.map((a) =>
          a.columnIndex === columnIndex ? { ...a, tag: newTag } : a
        )
      );
    },
    []
  );

  const handleSaveTemplate = useCallback(() => {
    if (!vendorId) return;

    const mappings: ColumnMappingEntry[] = assignments
      .filter((a) => a.tag !== null)
      .map((a) => ({
        column_index: a.columnIndex,
        header: a.header,
        tag: a.tag!,
      }));

    saveTemplateMutation.mutate(
      { vendor_id: vendorId, mappings },
      {
        onSuccess: () => {
          setSaveSuccess(true);
          setTimeout(() => setSaveSuccess(false), 3000);
        },
      }
    );
  }, [vendorId, assignments, saveTemplateMutation]);

  const handleApplyTemplate = useCallback(() => {
    if (!templateQuery.data) return;

    const templateMappings = templateQuery.data.mappings;
    setAssignments((prev) =>
      prev.map((a) => {
        const templateEntry = templateMappings.find(
          (m) => m.column_index === a.columnIndex
        );
        if (templateEntry) {
          return { ...a, tag: templateEntry.tag as TransactionTypeTag };
        }
        return a;
      })
    );
    setTemplateApplied(true);
  }, [templateQuery.data]);

  const handleConfirmMapping = useCallback(() => {
    if (!onMappingConfirmed) return;

    const mappings: ColumnMappingEntry[] = assignments
      .filter((a) => a.tag !== null)
      .map((a) => ({
        column_index: a.columnIndex,
        header: a.header,
        tag: a.tag!,
      }));

    onMappingConfirmed(mappings);
  }, [assignments, onMappingConfirmed]);

  // ─── Render Helpers ──────────────────────────────────────────────────────────

  const renderColumnHeader = (colIdx: number) => {
    const assignment = assignments[colIdx];
    if (!assignment) return null;

    return (
      <div className="flex flex-column gap-2">
        {/* Header name */}
        <span className="font-semibold text-sm">
          {assignment.header}
        </span>

        {/* Suggestion badge */}
        {assignment.suggestion?.suggested_tag && (
          <div className="flex align-items-center gap-1">
            <Tag
              value={assignment.suggestion.confidence ?? ''}
              severity={getConfidenceSeverity(assignment.suggestion.confidence)}
              style={{ fontSize: '0.7rem' }}
            />
            <span className="text-xs text-color-secondary">
              {assignment.suggestion.suggested_tag.replace(/_/g, ' ')}
            </span>
          </div>
        )}

        {/* Dropdown for tag assignment */}
        <Dropdown
          value={assignment.tag}
          options={TAG_OPTIONS}
          onChange={(e) => handleTagChange(colIdx, e.value)}
          placeholder="Select tag..."
          showClear
          className="w-full text-sm"
          style={{ minWidth: '140px' }}
          aria-label={`Tag assignment for column ${assignment.header}`}
        />
      </div>
    );
  };

  // ─── Render ──────────────────────────────────────────────────────────────────

  return (
    <div className="column-mapping-panel">
      {/* File Upload Section */}
      <div className="em-card mb-3">
        <h3 className="mt-0 mb-3">Upload Vendor Statement</h3>
        <FileUpload
          mode="basic"
          accept=".csv,.xlsx"
          maxFileSize={10000000}
          chooseLabel="Select File"
          auto={false}
          onSelect={handleFileSelect}
          disabled={isLoading}
          aria-label="Upload vendor statement file"
        />
        {filename && (
          <p className="mt-2 text-sm text-color-secondary">
            File: <strong>{filename}</strong> ({totalRowCount} rows total)
          </p>
        )}
      </div>

      {/* Loading State */}
      {isLoading && (
        <div className="flex align-items-center justify-content-center p-4">
          <ProgressSpinner
            style={{ width: '40px', height: '40px' }}
            aria-label="Loading file preview"
          />
          <span className="ml-2">Processing file...</span>
        </div>
      )}

      {/* Error State */}
      {previewMutation.isError && (
        <Message
          severity="error"
          text={
            previewMutation.error?.message ??
            'Failed to upload file. Please try again.'
          }
          className="w-full mb-3"
        />
      )}

      {/* Preview DataTable */}
      {hasPreview && !isLoading && (
        <div className="em-card mb-3">
          <div className="flex align-items-center justify-content-between mb-3">
            <h3 className="m-0">Data Preview (First 10 Rows)</h3>

            {/* Template Buttons */}
            <div className="flex gap-2">
              {vendorId && templateQuery.data && (
                <Button
                  label="Apply Template"
                  icon="pi pi-download"
                  severity="secondary"
                  size="small"
                  onClick={handleApplyTemplate}
                  disabled={templateApplied}
                  aria-label="Apply saved column mapping template"
                />
              )}
              {vendorId && (
                <Button
                  label="Save Template"
                  icon="pi pi-save"
                  size="small"
                  onClick={handleSaveTemplate}
                  loading={saveTemplateMutation.isPending}
                  disabled={
                    assignments.every((a) => a.tag === null) ||
                    saveTemplateMutation.isPending
                  }
                  aria-label="Save column mapping as template"
                />
              )}
            </div>
          </div>

          {/* Save Success Feedback */}
          {saveSuccess && (
            <Message
              severity="success"
              text="Template saved successfully."
              className="w-full mb-3"
            />
          )}

          {/* Save Error Feedback */}
          {saveTemplateMutation.isError && (
            <Message
              severity="error"
              text={
                saveTemplateMutation.error?.message ??
                'Failed to save template.'
              }
              className="w-full mb-3"
            />
          )}

          {/* Template Applied Indicator */}
          {templateApplied && (
            <Message
              severity="info"
              text="Template applied. You can modify the mappings before confirming."
              className="w-full mb-3"
            />
          )}

          {/* Auto-mapping legend */}
          <div className="flex align-items-center gap-3 mb-3">
            <span className="text-sm font-semibold">Confidence:</span>
            <Badge value="High" severity="success" />
            <Badge value="Medium" severity="warning" />
            <Badge value="Low" severity="secondary" />
          </div>

          {/* Data Preview Table */}
          <DataTable
            value={tableData}
            scrollable
            scrollHeight="400px"
            size="small"
            showGridlines
            emptyMessage="No data available."
            aria-label="File data preview with column mapping"
          >
            {previewHeaders.map((_header, colIdx) => (
              <Column
                key={`col_${colIdx}`}
                field={`col_${colIdx}`}
                header={renderColumnHeader(colIdx)}
                style={{ minWidth: '180px' }}
              />
            ))}
          </DataTable>

          {/* Confirm Mapping Button */}
          {onMappingConfirmed && (
            <div className="flex justify-content-end mt-3">
              <Button
                label="Confirm Mapping"
                icon="pi pi-check"
                onClick={handleConfirmMapping}
                disabled={assignments.every((a) => a.tag === null)}
                aria-label="Confirm column mapping and proceed"
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
};
