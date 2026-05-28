import { redirect } from 'next/navigation';

export default function SecurityPage() {
  redirect('/portal/security/scans');
}
