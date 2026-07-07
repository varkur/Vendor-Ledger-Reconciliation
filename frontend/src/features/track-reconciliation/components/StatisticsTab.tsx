/**
 * Statistics Tab — Pie charts for Statement Status and Reconciliation Status,
 * Amount Statistics, Reason for Difference, and Action Summary.
 */

export const StatisticsTab = () => {
  return (
    <div>
      {/* Reminder Info Bar */}
      <div className="em-info-bar">
        <span>Reminder Info</span>
        <span>No of Reminder Sent: 3/5 | Last Reminder date: 07 Jun 2026, 10:02 AM</span>
      </div>

      {/* Charts Row */}
      <div className="grid mb-4">
        {/* Statement Status */}
        <div className="col-12 md:col-6">
          <div className="em-stat-card">
            <h4 style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              Statement Status
              <i className="pi pi-info-circle" style={{ fontSize: 12, color: 'var(--color-text-muted)' }} />
              <span style={{ marginLeft: 'auto', fontSize: 14, fontWeight: 700 }}>366</span>
            </h4>
            <div className="flex align-items-center gap-4">
              {/* Pie chart placeholder */}
              <div
                style={{
                  width: 140,
                  height: 140,
                  borderRadius: '50%',
                  background: 'conic-gradient(#2196F3 0% 37%, #FF9800 37% 100%)',
                  flexShrink: 0,
                }}
              />
              <div className="flex flex-column gap-2">
                <div className="flex align-items-center gap-2">
                  <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#2196F3' }} />
                  <span className="text-sm">Responded</span>
                  <span className="ml-auto font-semibold">134</span>
                </div>
                <div className="flex align-items-center gap-2">
                  <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#FF9800' }} />
                  <span className="text-sm">Not Responded</span>
                  <span className="ml-auto font-semibold">231</span>
                </div>
                <div className="flex align-items-center gap-2">
                  <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#F44336' }} />
                  <span className="text-sm">Rejected</span>
                  <span className="ml-auto font-semibold">1</span>
                </div>
                <div className="flex align-items-center gap-2">
                  <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#9E9E9E' }} />
                  <span className="text-sm">Failed</span>
                  <span className="ml-auto font-semibold">0</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Reconciliation Status */}
        <div className="col-12 md:col-6">
          <div className="em-stat-card">
            <h4 style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              Reconciliation Status
              <i className="pi pi-info-circle" style={{ fontSize: 12, color: 'var(--color-text-muted)' }} />
              <span style={{ marginLeft: 'auto', fontSize: 14, fontWeight: 700 }}>134</span>
            </h4>
            <div className="flex align-items-center gap-4">
              {/* Pie chart placeholder */}
              <div
                style={{
                  width: 140,
                  height: 140,
                  borderRadius: '50%',
                  background: 'conic-gradient(#FF9800 0% 40%, #4CAF50 40% 62%, #2196F3 62% 68%, #9C27B0 68% 73%, #F44336 73% 78%, #00BCD4 78% 100%)',
                  flexShrink: 0,
                }}
              />
              <div className="grid" style={{ flex: 1 }}>
                <div className="col-6">
                  <div className="flex flex-column gap-2">
                    <div className="flex align-items-center gap-2 text-sm">
                      <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#2196F3' }} />
                      <span>Responded</span>
                      <span className="ml-auto font-semibold">0</span>
                    </div>
                    <div className="flex align-items-center gap-2 text-sm">
                      <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#4CAF50' }} />
                      <span>Statement Received</span>
                      <span className="ml-auto font-semibold">0</span>
                    </div>
                    <div className="flex align-items-center gap-2 text-sm">
                      <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#9C27B0' }} />
                      <span>Balance Confirmed</span>
                      <span className="ml-auto font-semibold">0</span>
                    </div>
                    <div className="flex align-items-center gap-2 text-sm">
                      <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#F44336' }} />
                      <span>Reco Rejected</span>
                      <span className="ml-auto font-semibold">0</span>
                    </div>
                    <div className="flex align-items-center gap-2 text-sm">
                      <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#FF9800' }} />
                      <span>Signoff Requested</span>
                      <span className="ml-auto font-semibold">7</span>
                    </div>
                    <div className="flex align-items-center gap-2 text-sm">
                      <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#795548' }} />
                      <span>Query Raised</span>
                      <span className="ml-auto font-semibold">1</span>
                    </div>
                    <div className="flex align-items-center gap-2 text-sm">
                      <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#00BCD4' }} />
                      <span>Signoff Completed</span>
                      <span className="ml-auto font-semibold">9</span>
                    </div>
                  </div>
                </div>
                <div className="col-6">
                  <div className="flex flex-column gap-2">
                    <div className="flex align-items-center gap-2 text-sm">
                      <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#E91E63' }} />
                      <span>Review Pending</span>
                      <span className="ml-auto font-semibold">5</span>
                    </div>
                    <div className="flex align-items-center gap-2 text-sm">
                      <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#3F51B5' }} />
                      <span>Reviewed</span>
                      <span className="ml-auto font-semibold">8</span>
                    </div>
                    <div className="flex align-items-center gap-2 text-sm">
                      <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#FF9800' }} />
                      <span>Mapping Pending</span>
                      <span className="ml-auto font-semibold">53</span>
                    </div>
                    <div className="flex align-items-center gap-2 text-sm">
                      <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#4CAF50' }} />
                      <span>Statement Mapped</span>
                      <span className="ml-auto font-semibold">21</span>
                    </div>
                    <div className="flex align-items-center gap-2 text-sm">
                      <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#009688' }} />
                      <span>In Progress</span>
                      <span className="ml-auto font-semibold">1</span>
                    </div>
                    <div className="flex align-items-center gap-2 text-sm">
                      <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#4CAF50' }} />
                      <span>Auto Completed</span>
                      <span className="ml-auto font-semibold">29</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Amount Statistics */}
      <div className="em-stat-card mb-4">
        <h4>Amount Statistics (Amt in Lakhs)</h4>
        <div className="grid align-items-center">
          <div className="col-12 md:col-5">
            {/* Progress bars */}
            <div className="mb-3">
              <div className="flex align-items-center justify-content-between mb-1">
                <span className="text-sm">Vendor Payable (INR -2,691.96)</span>
                <span className="text-sm font-semibold">30%</span>
              </div>
              <div className="em-progress-bar">
                <div className="em-progress-bar-fill primary" style={{ width: '30%' }} />
              </div>
            </div>
            <div className="mb-3">
              <div className="flex align-items-center justify-content-between mb-1">
                <span className="text-sm">Vendor Advance (INR 230.43)</span>
                <span className="text-sm font-semibold">19%</span>
              </div>
              <div className="em-progress-bar" style={{ background: '#FFFBEB' }}>
                <div className="em-progress-bar-fill warning" style={{ width: '19%' }} />
              </div>
            </div>
          </div>
          <div className="col-12 md:col-7">
            <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--color-surface-border)' }}>
                  <th style={{ padding: '8px', textAlign: 'left', fontWeight: 600 }}>Category</th>
                  <th style={{ padding: '8px', textAlign: 'right', fontWeight: 600 }}>Total Company Amt</th>
                  <th style={{ padding: '8px', textAlign: 'right', fontWeight: 600 }}>Company Amt Responded [A]</th>
                  <th style={{ padding: '8px', textAlign: 'right', fontWeight: 600 }}>Party Amt Responded [B]</th>
                  <th style={{ padding: '8px', textAlign: 'right', fontWeight: 600 }}>Net Difference [C]=[A]+[B]</th>
                </tr>
              </thead>
              <tbody>
                <tr style={{ borderBottom: '1px solid var(--color-surface-border)' }}>
                  <td style={{ padding: '8px' }}>Vendor Payable</td>
                  <td style={{ padding: '8px', textAlign: 'right' }}>-8,984.84</td>
                  <td style={{ padding: '8px', textAlign: 'right' }}>-2,691.96</td>
                  <td style={{ padding: '8px', textAlign: 'right' }}>1,327.34</td>
                  <td style={{ padding: '8px', textAlign: 'right' }}>-1,364.62</td>
                </tr>
                <tr>
                  <td style={{ padding: '8px' }}>Vendor Advance</td>
                  <td style={{ padding: '8px', textAlign: 'right' }}>1,221.23</td>
                  <td style={{ padding: '8px', textAlign: 'right' }}>230.43</td>
                  <td style={{ padding: '8px', textAlign: 'right' }}>-127.61</td>
                  <td style={{ padding: '8px', textAlign: 'right' }}>102.82</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Reason for Difference & Action Summary */}
      <div className="grid">
        <div className="col-12 md:col-6">
          <div className="em-stat-card">
            <div className="flex align-items-center justify-content-between mb-3">
              <h4 style={{ margin: 0 }}>Reason for Difference (Amt in Lakhs)</h4>
              <span className="link-view text-sm">Show All</span>
            </div>
            <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--color-surface-border)' }}>
                  <th style={{ padding: '8px', textAlign: 'left', fontWeight: 600 }}>Status</th>
                  <th style={{ padding: '8px', textAlign: 'right', fontWeight: 600 }}>Difference Amt</th>
                  <th style={{ padding: '8px', textAlign: 'right', fontWeight: 600 }}>No. of Entries</th>
                </tr>
              </thead>
              <tbody>
                <tr style={{ borderBottom: '1px solid var(--color-surface-border)' }}>
                  <td style={{ padding: '8px' }}>Closing Balance Difference</td>
                  <td style={{ padding: '8px', textAlign: 'right' }}>7763.60</td>
                  <td style={{ padding: '8px', textAlign: 'right' }}>366</td>
                </tr>
                <tr style={{ borderBottom: '1px solid var(--color-surface-border)' }}>
                  <td style={{ padding: '8px' }}>Payment not booked by Party</td>
                  <td style={{ padding: '8px', textAlign: 'right' }}>667.56</td>
                  <td style={{ padding: '8px', textAlign: 'right' }}>117</td>
                </tr>
                <tr style={{ borderBottom: '1px solid var(--color-surface-border)' }}>
                  <td style={{ padding: '8px' }}>Invoice not booked by Party</td>
                  <td style={{ padding: '8px', textAlign: 'right' }}>-450.29</td>
                  <td style={{ padding: '8px', textAlign: 'right' }}>124</td>
                </tr>
                <tr style={{ borderBottom: '1px solid var(--color-surface-border)' }}>
                  <td style={{ padding: '8px' }}>Invoice not booked by Company</td>
                  <td style={{ padding: '8px', textAlign: 'right' }}>416.61</td>
                  <td style={{ padding: '8px', textAlign: 'right' }}>152</td>
                </tr>
                <tr>
                  <td style={{ padding: '8px' }}>Payment not booked by Company</td>
                  <td style={{ padding: '8px', textAlign: 'right' }}>-255.15</td>
                  <td style={{ padding: '8px', textAlign: 'right' }}>61</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
        <div className="col-12 md:col-6">
          <div className="em-stat-card">
            <h4>Action Summary (Amt in Lakhs)</h4>
            <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--color-surface-border)' }}>
                  <th style={{ padding: '8px', textAlign: 'left', fontWeight: 600 }}>Action Taken Status</th>
                  <th style={{ padding: '8px', textAlign: 'right', fontWeight: 600 }}>Amt</th>
                  <th style={{ padding: '8px', textAlign: 'right', fontWeight: 600 }}>No. of Entries</th>
                </tr>
              </thead>
              <tbody>
                <tr style={{ borderBottom: '1px solid var(--color-surface-border)' }}>
                  <td style={{ padding: '8px' }}>Total Differences</td>
                  <td style={{ padding: '8px', textAlign: 'right' }}>15.22</td>
                  <td style={{ padding: '8px', textAlign: 'right' }}>159</td>
                </tr>
                <tr style={{ borderBottom: '1px solid var(--color-surface-border)' }}>
                  <td style={{ padding: '8px' }}>Pending with Party</td>
                  <td style={{ padding: '8px', textAlign: 'right' }}>37.01</td>
                  <td style={{ padding: '8px', textAlign: 'right' }}>62</td>
                </tr>
                <tr style={{ borderBottom: '1px solid var(--color-surface-border)' }}>
                  <td style={{ padding: '8px' }}>Pending with Company</td>
                  <td style={{ padding: '8px', textAlign: 'right' }}>-21.80</td>
                  <td style={{ padding: '8px', textAlign: 'right' }}>95</td>
                </tr>
                <tr>
                  <td style={{ padding: '8px' }}>No Action Required</td>
                  <td style={{ padding: '8px', textAlign: 'right' }}>0.00</td>
                  <td style={{ padding: '8px', textAlign: 'right' }}>2</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
};
