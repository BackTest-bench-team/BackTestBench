/** Session/tab IDs — never use crypto.randomUUID (blocked on HTTP VMs). */
export function createId(): string {
  return `id-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}
