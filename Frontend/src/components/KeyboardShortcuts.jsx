import { useState, useEffect } from 'react';

export default function KeyboardShortcuts({ onStartStop, onListen }) {
  const [showHelp, setShowHelp] = useState(false);

  useEffect(() => {
    const handleKeyPress = (e) => {
      // Ignore if typing in an input field
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
        return;
      }

      const key = e.key.toLowerCase();
      
      if (key === 's') {
        onStartStop();
      } else if (key === 'l') {
        onListen();
      } else if (key === '?' || key === 'h') {
        setShowHelp(prev => !prev);
      }
    };

    window.addEventListener('keydown', handleKeyPress);
    return () => window.removeEventListener('keydown', handleKeyPress);
  }, [onStartStop, onListen]);

  return (
    <>
      {/* Help button */}
      <button
        className="help-button"
        onClick={() => setShowHelp(!showHelp)}
        title="Keyboard shortcuts (press ? or H)"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="12" cy="12" r="10" />
          <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
          <line x1="12" y1="17" x2="12.01" y2="17" />
        </svg>
      </button>

      {/* Shortcuts panel */}
      {showHelp && (
        <div className="shortcuts-overlay" onClick={() => setShowHelp(false)}>
          <div className="shortcuts-panel" onClick={(e) => e.stopPropagation()}>
            <div className="shortcuts-header">
              <h3>⌨️ Keyboard Shortcuts</h3>
              <button className="close-btn" onClick={() => setShowHelp(false)}>×</button>
            </div>
            <div className="shortcuts-list">
              <div className="shortcut-item">
                <kbd>S</kbd>
                <span>Start / Stop system</span>
              </div>
              <div className="shortcut-item">
                <kbd>L</kbd>
                <span>Listen (voice query)</span>
              </div>
              <div className="shortcut-item">
                <kbd>?</kbd>
                <span>Show/hide help menu</span>
              </div>
            </div>
            <div className="shortcuts-footer">
              Press <kbd>ESC</kbd> or click outside to close
            </div>
          </div>
        </div>
      )}
    </>
  );
}
