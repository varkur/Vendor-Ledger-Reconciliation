/**
 * Unit tests for PortalStatementPage sign-off navigation and dispute functionality.
 *
 * Verifies that the "Proceed to Sign-Off" button is enabled/disabled based on case status,
 * and that "Raise Dispute" button functions correctly.
 *
 * Requirements: 7, 8
 *
 * @vitest-environment jsdom
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, cleanup, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { PortalStatementPage } from './PortalStatementPage';

// Mock navigate
const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

// Mock portal context
vi.mock('./context/PortalContext', () => ({
  usePortalContext: () => ({
    portalToken: 'mock-token',
    caseInfo: { case_id: 'case-123', vendor_name: 'Test Vendor', status: 'matched' },
    isAuthenticated: true,
  }),
}));

// Mutable status for testing
let mockStatus = 'matched';
const mockMutate = vi.fn();

// Mock portal hooks
vi.mock('./hooks/usePortal', () => ({
  usePortalStatement: () => ({
    data: {
      case_id: 'case-123',
      vendor_name: 'Test Vendor',
      period_start: '2024-01-01',
      period_end: '2024-12-31',
      total_matched_entries: 10,
      total_unmatched_vendor: 2,
      vendor_opening_balance: 100000,
      vendor_closing_balance: 120000,
      net_difference: 5000,
      match_summary: [],
      statement_version: 'v1',
      get status() { return mockStatus; },
    },
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  }),
  useRaiseDispute: () => ({
    mutate: mockMutate,
    isPending: false,
  }),
  PORTAL_QUERY_KEY: 'vlr-vendor-portal',
}));

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <PortalStatementPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('PortalStatementPage — Sign-Off Navigation & Dispute', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockStatus = 'matched';
  });

  afterEach(() => {
    cleanup();
  });

  it('enables "Proceed to Sign-Off" button when status is "matched"', () => {
    mockStatus = 'matched';
    renderPage();

    const buttons = document.querySelectorAll('button[aria-label="Proceed to Sign-Off"]');
    expect(buttons.length).toBe(1);
    expect((buttons[0] as HTMLButtonElement).disabled).toBe(false);
  });

  it('disables "Proceed to Sign-Off" button when status is "disputed"', () => {
    mockStatus = 'disputed';
    renderPage();

    const buttons = document.querySelectorAll('button[aria-label="Proceed to Sign-Off"]');
    expect(buttons.length).toBe(1);
    expect((buttons[0] as HTMLButtonElement).disabled).toBe(true);
  });

  it('navigates to /portal/sign-off when button is clicked', () => {
    mockStatus = 'matched';
    renderPage();

    const button = document.querySelector('button[aria-label="Proceed to Sign-Off"]') as HTMLButtonElement;
    button.click();

    expect(mockNavigate).toHaveBeenCalledWith('/portal/sign-off');
  });

  it('does not navigate when button is disabled (disputed)', () => {
    mockStatus = 'disputed';
    renderPage();

    const button = document.querySelector('button[aria-label="Proceed to Sign-Off"]') as HTMLButtonElement;
    button.click();

    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it('renders "Raise Dispute" button enabled when status is not disputed', () => {
    mockStatus = 'matched';
    renderPage();

    const buttons = document.querySelectorAll('button[aria-label="Raise Dispute"]');
    expect(buttons.length).toBe(1);
    expect((buttons[0] as HTMLButtonElement).disabled).toBe(false);
  });

  it('disables "Raise Dispute" button when case is already disputed', () => {
    mockStatus = 'disputed';
    renderPage();

    const buttons = document.querySelectorAll('button[aria-label="Raise Dispute"]');
    expect(buttons.length).toBe(1);
    expect((buttons[0] as HTMLButtonElement).disabled).toBe(true);
  });

  it('shows status badge as DISPUTED when status is disputed', () => {
    mockStatus = 'disputed';
    renderPage();

    const badge = document.querySelector('.p-tag-value');
    expect(badge?.textContent).toBe('DISPUTED');
  });
});
