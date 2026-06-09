import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import Chat from '../pages/Chat';
import { vi } from 'vitest';

global.fetch = vi.fn(() => 
  Promise.resolve({
    json: () => Promise.resolve({ status: 'success', courses: ['Math'] })
  })
);

class MockWebSocket {
  constructor(url) {
    this.url = url;
    this.readyState = 1;
  }
  send = vi.fn();
  close = vi.fn();
  addEventListener = vi.fn();
  removeEventListener = vi.fn();
}
global.WebSocket = MockWebSocket;

describe('Chat Component', () => {
  beforeEach(() => {
    fetch.mockClear();
  });

  test('renders chat messages area', () => {
    render(<Chat />);
    expect(screen.getByPlaceholderText(/Ask about the slides.../i)).toBeInTheDocument();
  });

  test('sends message via websocket', () => {
    render(<Chat />);
    const input = screen.getByPlaceholderText(/Ask about the slides.../i);
    const form = input.closest('form');
    
    fireEvent.change(input, { target: { value: 'Test Question' } });
    fireEvent.submit(form);
    
    // Check state reset
    expect(input.value).toBe('');
  });
});
