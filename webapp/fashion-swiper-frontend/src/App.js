import React, { useState, useEffect } from 'react';
import { Heart, X, RotateCcw, TrendingUp, Lock } from 'lucide-react';
import { useDrag } from '@use-gesture/react';


const FashionSwipeApp = () => {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [password, setPassword] = useState('');
  const [authError, setAuthError] = useState('');
  const [token, setToken] = useState('');
  
  const [items, setItems] = useState([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [swipeDirection, setSwipeDirection] = useState(null);
  const [stats, setStats] = useState({ liked: 0, disliked: 0, total: 0 });
  const [isLoading, setIsLoading] = useState(false);

  const bind = useDrag(({ down, movement: [mx], direction: [xDir] }) => {
    // We'll consider it a swipe if the user drags more than a certain threshold (e.g., 50 pixels)
    const isSwipe = Math.abs(mx) > 50;

    // This code block only runs when the user releases their mouse/finger
    if (!down && isSwipe) {
      // direction: [xDir] gives us 1 for right and -1 for left.
      // We use a ternary operator to cleanly determine the direction.
      const swipeDirection = xDir > 0 ? 'right' : 'left';
      
      handleSwipe(swipeDirection);
    }
  });
  // Check for saved token
  useEffect(() => {
    const savedToken = window.localStorage?.getItem('fashion_token');
    if (savedToken) {
      setToken(savedToken);
      setIsAuthenticated(true);
      loadItems(savedToken);
    }
  }, []);

  const handleLogin = async () => {
    setAuthError('');
    
    try {
      const response = await fetch('/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password })
      });
      
      if (response.ok) {
        const data = await response.json();
        setToken(data.access_token);
        if (window.localStorage) {
          window.localStorage.setItem('fashion_token', data.access_token);
        }
        setIsAuthenticated(true);
        loadItems(data.access_token);
      } else {
        setAuthError('Invalid password');
      }
    } catch (error) {
      setAuthError('Connection error. Is the server running?');
    }
  };

  const loadItems = async (authToken) => {
    try {
      const response = await fetch('/api/next_item', {
        headers: {
          'Authorization': `Bearer ${authToken}`
        }
      });
      
      if (response.ok) {
        const item = await response.json();
        setItems([item]);
      }
    } catch (error) {
      console.error('Failed to load items:', error);
    }
  };

  const sendRatingToBackend = async (itemId, rating) => {
    try {
      await fetch('/api/rate', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ item_id: itemId, rating: rating })
      });
    } catch (error) {
      console.error('Failed to send rating:', error);
    }
  };

  const handleSwipe = async (direction) => {
    setSwipeDirection(direction);
    
    const newStats = { ...stats, total: stats.total + 1 };
    if (direction === 'right') {
      newStats.liked += 1;
    } else {
      newStats.disliked += 1;
    }
    setStats(newStats);

    await sendRatingToBackend(currentItem.id, direction === 'right' ? 1 : 0);

    setTimeout(async () => {
      setSwipeDirection(null);
      await loadItems(token);
    }, 300);
  };

  const handleUndo = () => {
    if (currentIndex > 0) {
      setCurrentIndex(currentIndex - 1);
      const lastDirection = stats.liked > stats.disliked ? 'liked' : 'disliked';
      setStats({
        ...stats,
        [lastDirection]: stats[lastDirection] - 1,
        total: stats.total - 1
      });
    }
  };

  const handleLogout = () => {
    if (window.localStorage) {
      window.localStorage.removeItem('fashion_token');
    }
    setIsAuthenticated(false);
    setToken('');
    setPassword('');
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter') {
      handleLogin();
    }
  };

  const handleImageClick = (url) => {
    if (url) {
      // This opens the URL in a new browser tab
      window.open(url, '_blank', 'noopener,noreferrer');
    }
  };

  // Login Screen
  if (!isAuthenticated) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-gray-900 to-gray-800 flex items-center justify-center p-4">
        <div className="bg-white rounded-2xl shadow-2xl p-8 w-full max-w-md">
          <div className="text-center mb-8">
            <div className="w-20 h-20 bg-gradient-to-br from-purple-500 to-pink-500 rounded-full mx-auto mb-4 flex items-center justify-center">
              <Lock className="w-10 h-10 text-white" />
            </div>
            <h1 className="text-3xl font-bold text-gray-900 mb-2">Fashion Trainer</h1>
            <p className="text-gray-600">Enter password to continue</p>
          </div>
          
          <div className="space-y-4">
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onKeyPress={handleKeyPress}
              placeholder="Password"
              className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
            />
            
            {authError && (
              <div className="bg-red-50 text-red-600 px-4 py-3 rounded-lg text-sm">
                {authError}
              </div>
            )}
            
            <button
              onClick={handleLogin}
              className="w-full bg-gradient-to-r from-purple-500 to-pink-500 text-white py-3 rounded-lg font-semibold hover:from-purple-600 hover:to-pink-600 transition-all"
            >
              Login
            </button>
          </div>
          
          <div className="mt-6 text-center text-sm text-gray-500">
            <p>🔒 Your data stays private</p>
            <p className="mt-1">Only you can access this app</p>
          </div>
        </div>
      </div>
    );
  }

  const currentItem = items[0];

  if (!currentItem) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-gray-900 to-gray-800 flex items-center justify-center">
        <div className="text-center text-white">
          <TrendingUp className="w-16 h-16 mx-auto mb-4 animate-pulse" />
          <h2 className="text-2xl font-bold mb-2">Loading items...</h2>
          <button
            onClick={handleLogout}
            className="text-gray-400 hover:text-white mt-4"
          >
            Logout
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 to-gray-800 flex flex-col overflow-y-auto">
      <div className="p-4 text-white">
        <div className="flex justify-between items-center mb-2">
          <h1 className="text-2xl font-bold">Fashion Trainer</h1>
          <button
            onClick={handleLogout}
            className="text-sm text-gray-400 hover:text-white"
          >
            Logout
          </button>
        </div>
        
        <div className="flex gap-4 text-sm">
          <div className="flex items-center gap-1">
            <Heart className="w-4 h-4 text-green-400" />
            <span>{stats.liked}</span>
          </div>
          <div className="flex items-center gap-1">
            <X className="w-4 h-4 text-red-400" />
            <span>{stats.disliked}</span>
          </div>
          <div className="text-gray-400">
            Total: {stats.total}
          </div>
        </div>
      </div>

      <div className="flex-1 flex items-center justify-center p-4">
        <div {...bind()} className={`relative w-full max-w-md transition-all duration-300 ${
            swipeDirection === 'right' ? 'translate-x-full opacity-0' : 
            swipeDirection === 'left' ? '-translate-x-full opacity-0' : ''
          }`}
        >
          <div className="bg-white rounded-2xl shadow-2xl overflow-hidden">
            <div className="relative h-96 bg-gray-200">
              <img
                src={currentItem.image}
                alt={currentItem.title}
                className="w-full h-full object-cover cursor-pointer" // <<< Added cursor-pointer
                onClick={() => handleImageClick(currentItem.url)}   // <<< Added this onClick handler
              />
              
              {swipeDirection === 'right' && (
                <div className="absolute inset-0 bg-green-500 bg-opacity-20 flex items-center justify-center">
                  <Heart className="w-32 h-32 text-green-500" strokeWidth={3} />
                </div>
              )}
              {swipeDirection === 'left' && (
                <div className="absolute inset-0 bg-red-500 bg-opacity-20 flex items-center justify-center">
                  <X className="w-32 h-32 text-red-500" strokeWidth={3} />
                </div>
              )}
            </div>

            <div className="p-6">
              <h2 className="text-2xl font-bold mb-2">{currentItem.title}</h2>
              <div className="flex justify-between items-center text-gray-600">
                <span className="font-semibold">{currentItem.brand}</span>
                <span className="text-xl font-bold text-gray-900">{currentItem.price}</span>
              </div>
            </div>
          </div>

          <div className="flex justify-center gap-6 mt-6">
            <button
              onClick={() => handleSwipe('left')}
              className="w-16 h-16 bg-white rounded-full shadow-lg flex items-center justify-center hover:scale-110 transition-transform active:scale-95"
            >
              <X className="w-8 h-8 text-red-500" strokeWidth={2.5} />
            </button>

            <button
              onClick={handleUndo}
              disabled={currentIndex === 0}
              className="w-14 h-14 bg-white rounded-full shadow-lg flex items-center justify-center hover:scale-110 transition-transform active:scale-95 disabled:opacity-50"
            >
              <RotateCcw className="w-6 h-6 text-yellow-500" />
            </button>

            <button
              onClick={() => handleSwipe('right')}
              className="w-16 h-16 bg-white rounded-full shadow-lg flex items-center justify-center hover:scale-110 transition-transform active:scale-95"
            >
              <Heart className="w-8 h-8 text-green-500" strokeWidth={2.5} />
            </button>
          </div>
        </div>
      </div>

      <div className="p-4 text-center text-gray-400 text-sm">
        Swipe right for items you like, left for items you don't
      </div>
    </div>
  );
};

export default FashionSwipeApp;