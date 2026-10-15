export interface AppNotification {
  id: string;
  event: string;
  title: string;
  body: string;
  /** Path in the app to open, e.g. /bookings/<id>. */
  link: string | null;
  created_at: string;
  read_at: string | null;
}

export interface Inbox {
  items: AppNotification[];
  unread: number;
}

export interface NotificationPreferences {
  email_enabled: boolean;
  push_enabled: boolean;
  note: string;
}
