import { redirect } from 'next/navigation';

export default function SystemAIRedirect() {
  redirect('/settings/ai-configuration');
}
