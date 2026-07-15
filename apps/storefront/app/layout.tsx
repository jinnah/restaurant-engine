import type { Metadata } from 'next';
import type { ReactNode } from 'react';
import './globals.css';
import styles from './layout.module.css';

export const metadata: Metadata = {
  title: 'Restaurant Engine Storefront',
  description: 'Foundation of the Restaurant Engine public storefront.',
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className={styles.header}>
          <p className={styles.wordmark}>Restaurant Engine</p>
        </header>
        <main className={styles.main}>{children}</main>
        <footer className={styles.footer}>
          <p>Restaurant Engine — public storefront</p>
        </footer>
      </body>
    </html>
  );
}
