import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App.jsx';
import './styles/main.css';

class ErrorBoundary extends React.Component {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(error, info) {
    console.error('Unhandled interface error:', error, info.componentStack);
  }
  render() {
    if (this.state.failed) return <main className="shell"><h1>Something went wrong</h1><p>Reload the page to reconnect. Your saved timetables remain in MongoDB.</p><button onClick={() => location.reload()}>Reload</button></main>;
    return this.props.children;
  }
}

ReactDOM.createRoot(document.getElementById('root')).render(<React.StrictMode><ErrorBoundary><App /></ErrorBoundary></React.StrictMode>);
