import { BrowserRouter, Navigate, Route, Routes } from 'react-router';

import { Layout } from './components/layout';
import { Loading } from './components/ui';
import { AuthProvider, useAuth } from './lib/auth';
import { AuditPage } from './pages/audit';
import { BookingDetailPage, BookingsPage } from './pages/bookings';
import { DeliveriesPage, DeliveryDetailPage } from './pages/deliveries';
import { LoginPage } from './pages/login';
import { NotificationsPage } from './pages/notifications';
import { OverviewPage } from './pages/overview';
import { PaymentsPage } from './pages/payments';
import { UsersPage } from './pages/users';
import { VehicleDetailPage, VehiclesPage } from './pages/vehicles';
import { VerificationDetailPage, VerificationsPage } from './pages/verifications';

export function AppRoutes() {
  const { state } = useAuth();
  if (state.status === 'loading') return <Loading label="Starting…" />;
  if (state.status === 'signedOut') return <LoginPage expired={state.expired} />;
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<OverviewPage />} />
        <Route path="verifications" element={<VerificationsPage />} />
        <Route path="verifications/:id" element={<VerificationDetailPage />} />
        <Route path="vehicles" element={<VehiclesPage />} />
        <Route path="vehicles/:id" element={<VehicleDetailPage />} />
        <Route path="bookings" element={<BookingsPage />} />
        <Route path="bookings/:id" element={<BookingDetailPage />} />
        <Route path="payments" element={<PaymentsPage />} />
        <Route path="deliveries" element={<DeliveriesPage />} />
        <Route path="deliveries/:id" element={<DeliveryDetailPage />} />
        <Route path="users" element={<UsersPage />} />
        <Route path="notifications" element={<NotificationsPage />} />
        <Route path="audit" element={<AuditPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

export function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </AuthProvider>
  );
}
