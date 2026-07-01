/**
 * Generic Content Viewer Dialog.
 * Renders content based on type: JSON (formatted), plain text, or PDF.
 * Reusable across the application wherever content preview is needed.
 *
 * @example
 * <ContentViewerDialog
 *   visible={showViewer}
 *   onHide={() => setShowViewer(false)}
 *   title="Audit Log Details"
 *   content={jsonString}
 *   contentType="json"
 * />
 */

import React, { useMemo } from 'react';
import { Dialog } from 'primereact/dialog';
import { Button } from 'primereact/button';

export type ContentType = 'json' | 'text' | 'pdf' | 'html';

interface ContentViewerDialogProps {
  /** Controls dialog visibility */
  visible: boolean;
  /** Callback to close the dialog */
  onHide: () => void;
  /** Dialog header title */
  title?: string;
  /** Raw content string to display */
  content: string | null;
  /** Type of content — determines rendering strategy */
  contentType?: ContentType;
  /** Optional: URL for PDF or external content */
  contentUrl?: string;
  /** Dialog width */
  width?: string;
}

export const ContentViewerDialog: React.FC<ContentViewerDialogProps> = ({
  visible,
  onHide,
  title = 'Content Viewer',
  content,
  contentType = 'json',
  contentUrl,
  width = '650px',
}) => {
  const formattedContent = useMemo(() => {
    if (!content) return null;

    switch (contentType) {
      case 'json':
        try {
          const parsed = JSON.parse(content);
          return JSON.stringify(parsed, null, 2);
        } catch {
          return content;
        }
      case 'text':
      case 'html':
      default:
        return content;
    }
  }, [content, contentType]);

  const handleCopy = async () => {
    if (formattedContent) {
      await navigator.clipboard.writeText(formattedContent);
    }
  };

  const footer = (
    <div className="flex justify-content-between align-items-center">
      <span className="text-xs text-500">
        {contentType.toUpperCase()}
        {formattedContent ? ` • ${formattedContent.length} chars` : ''}
      </span>
      <div className="flex gap-2">
        <Button
          label="Copy"
          icon="pi pi-copy"
          size="small"
          severity="secondary"
          outlined
          onClick={handleCopy}
          aria-label="Copy content to clipboard"
        />
        <Button
          label="Close"
          icon="pi pi-times"
          size="small"
          severity="secondary"
          text
          onClick={onHide}
        />
      </div>
    </div>
  );

  const renderContent = () => {
    if (!content && !contentUrl) {
      return (
        <div className="text-center text-500 py-4">
          <i className="pi pi-inbox text-4xl mb-3 block" />
          <p>No content to display</p>
        </div>
      );
    }

    switch (contentType) {
      case 'json':
        return <JsonViewer content={formattedContent || ''} />;
      case 'pdf':
        return <PdfViewer url={contentUrl || ''} />;
      case 'html':
        return (
          <div
            className="p-3 border-round surface-ground overflow-auto"
            style={{ maxHeight: '500px' }}
            dangerouslySetInnerHTML={{ __html: content || '' }}
          />
        );
      case 'text':
      default:
        return (
          <pre
            className="p-3 border-round surface-ground text-sm overflow-auto m-0"
            style={{ maxHeight: '500px', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}
          >
            {formattedContent}
          </pre>
        );
    }
  };

  return (
    <Dialog
      header={title}
      visible={visible}
      style={{ width }}
      modal
      dismissableMask
      onHide={onHide}
      footer={footer}
      contentClassName="p-0"
    >
      <div className="p-3">{renderContent()}</div>
    </Dialog>
  );
};

// ─── JSON Viewer Sub-component ───

interface JsonViewerProps {
  content: string;
}

const JsonViewer: React.FC<JsonViewerProps> = ({ content }) => {
  // Simple syntax highlighting for JSON
  const highlighted = useMemo(() => {
    return content
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      // Strings (keys and values)
      .replace(/"([^"]+)"(?=\s*:)/g, '<span style="color:#9C27B0">"$1"</span>')  // keys
      .replace(/:\s*"([^"]*)"/g, ': <span style="color:#2E7D32">"$1"</span>')     // string values
      // Numbers
      .replace(/:\s*(\d+\.?\d*)/g, ': <span style="color:#1565C0">$1</span>')
      // Booleans & null
      .replace(/:\s*(true|false|null)/g, ': <span style="color:#E65100">$1</span>');
  }, [content]);

  return (
    <div
      className="border-round overflow-auto"
      style={{
        maxHeight: '500px',
        background: '#FAFAFA',
        border: '1px solid var(--surface-border)',
      }}
    >
      <pre
        className="m-0 p-3 text-sm"
        style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', lineHeight: '1.6' }}
        dangerouslySetInnerHTML={{ __html: highlighted }}
      />
    </div>
  );
};

// ─── PDF Viewer Sub-component ───

interface PdfViewerProps {
  url: string;
}

const PdfViewer: React.FC<PdfViewerProps> = ({ url }) => {
  if (!url) {
    return <p className="text-500 text-center">No PDF URL provided</p>;
  }
  return (
    <iframe
      src={url}
      title="PDF Viewer"
      className="w-full border-none border-round"
      style={{ height: '600px' }}
    />
  );
};
