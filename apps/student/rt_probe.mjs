// Subscribes with the browser's publishable key exactly as the portals do,
// then reports what arrives.
import { createClient } from '@supabase/supabase-js';
import ws from 'ws';
const [url, key] = [process.env.U, process.env.K];
const supabase = createClient(url, key, { auth: { persistSession: false }, realtime: { transport: ws } });

const seen = [];
const ch = supabase.channel('probe')
  .on('postgres_changes', { event: 'INSERT', schema: 'public', table: 'chat_events' },
      (p) => seen.push(p.new))
  .subscribe((status) => console.log('channel status:', status));

setTimeout(async () => {
  console.log('events received:', JSON.stringify(seen));
  // Prove the socket cannot reach message bodies with this key.
  const { error } = await supabase.from('conversation_messages').select('id,body').limit(1);
  console.log('direct message read:', error ? `blocked (${error.code || error.message})` : 'ALLOWED - LEAK');
  await supabase.removeChannel(ch);
  process.exit(0);
}, 25000);
