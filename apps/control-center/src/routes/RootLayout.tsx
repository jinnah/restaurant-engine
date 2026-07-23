import { Outlet } from 'react-router';
import styles from './RootLayout.module.css';

export function RootLayout() {
  return (
    <>
      <header className={styles.header}>
        <p className={styles.wordmark}>Restaurant Engine</p>
      </header>
      <main className={styles.main}>
        <Outlet />
      </main>
      <footer className={styles.footer}>
        <p>Restaurant Engine</p>
      </footer>
    </>
  );
}
