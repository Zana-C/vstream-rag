import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import VideoProcessor from '../pages/VideoProcessor';
import { vi } from 'vitest';

global.fetch = vi.fn(() => 
  Promise.resolve({
    json: () => Promise.resolve({ status: 'success', courses: ['Math'] })
  })
);

describe('VideoProcessor Component', () => {
  beforeEach(() => {
    fetch.mockClear();
  });

  test('renders upload section and sliders', async () => {
    render(<VideoProcessor />);
    expect(screen.getByText(/Upload Lecture Video/i)).toBeInTheDocument();
    expect(screen.getByText(/Sample Rate/i)).toBeInTheDocument();
  });

  test('slider changes update state', () => {
    render(<VideoProcessor />);
    const sliders = screen.getAllByRole('slider');
    const sampleRateSlider = sliders[0];
    
    fireEvent.change(sampleRateSlider, { target: { value: '2.5' } });
    expect(sampleRateSlider.value).toBe('2.5');
  });

  test('file upload triggers process API', async () => {
    // Mock the second fetch call (the first is courses)
    fetch.mockImplementation((url) => {
      if (url.includes('courses')) {
        return Promise.resolve({ json: () => Promise.resolve({ status: 'success', courses: ['Math'] }) });
      }
      return Promise.resolve({ json: () => Promise.resolve({ status: 'success', slides: [{ id: 1, text: 'Test slide' }] }) });
    });
    
    render(<VideoProcessor />);
    const input = document.querySelector('input[type="file"]');
    const file = new File(['dummy content'], 'test.mp4', { type: 'video/mp4' });
    
    fireEvent.change(input, { target: { files: [file] } });
    
    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith('http://localhost:8000/api/video/process', expect.any(Object));
    });
  });
});
