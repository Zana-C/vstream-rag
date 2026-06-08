import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import DatabaseManager from '../pages/DatabaseManager';
import { vi } from 'vitest';

global.fetch = vi.fn((url) => {
  if (url.includes('courses')) {
    return Promise.resolve({ json: () => Promise.resolve({ status: 'success', courses: ['Math'] }) });
  }
  return Promise.resolve({ json: () => Promise.resolve({ status: 'success', slides: [{id: 1, course: 'Math', text: 'Q1'}] }) });
});

global.confirm = vi.fn(() => true);

describe('DatabaseManager Component', () => {
  beforeEach(() => {
    fetch.mockClear();
  });

  test('renders database table', async () => {
    render(<DatabaseManager />);
    expect(screen.getByText(/Database Manager/i)).toBeInTheDocument();
    
    await waitFor(() => {
      expect(screen.getByText('Q1')).toBeInTheDocument();
    });
  });

  test('delete slide', async () => {
    global.fetch.mockImplementation((url, options) => {
      if (url.includes('courses')) return Promise.resolve({ json: () => Promise.resolve({ status: 'success', courses: ['Math'] }) });
      if (options && options.method === 'DELETE') {
        return Promise.resolve({ json: () => Promise.resolve({ status: 'success' }) });
      }
      return Promise.resolve({ json: () => Promise.resolve({ status: 'success', slides: [{id: 1, course: 'Math', text: 'Q1'}] }) });
    });

    render(<DatabaseManager />);
    await waitFor(() => {
      expect(screen.getByText('Q1')).toBeInTheDocument();
    });

    // Find the second button which is Trash2 (delete button has stroke-linecap polyline etc)
    // We can query by role or just find all buttons
    const btns = Array.from(document.querySelectorAll('button'));
    const delBtn = btns[btns.length - 1]; // Last button is trash
    
    if (delBtn) {
      fireEvent.click(delBtn);
      await waitFor(() => {
        expect(global.confirm).toHaveBeenCalled();
        expect(fetch).toHaveBeenCalledWith(expect.stringContaining('api/slides/1'), expect.objectContaining({ method: 'DELETE' }));
      });
    }
  });
});
