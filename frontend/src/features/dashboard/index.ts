// Dashboard feature module barrel export

export { DashboardPage } from './pages/DashboardPage';
export { useDashboardWidgets, useRecentConfirmations } from './hooks/useDashboard';
export {
  getDashboardWidgets,
  getRecentConfirmations,
  type DashboardWidgets,
  type RecentConfirmation,
  type RecentConfirmationsResponse,
} from './api/dashboardApi';
