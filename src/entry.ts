const query = new URLSearchParams(location.search);
if (query.has('workspace') || query.has('capture') || query.has('immersive')) {
  await import('./main');
} else {
  document.getElementById('app')!.id = 'demo';
  await import('./demo');
}
export {};
