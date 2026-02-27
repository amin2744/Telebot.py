const express = require('express');
const mongoose = require('mongoose');
const cors = require('cors');
require('dotenv').config();

const app = express();

// Middleware
app.use(cors());
app.use(express.json());

// Connect to MongoDB
mongoose.connect(process.env.MONGODB_URI, { useNewUrlParser: true, useUnifiedTopology: true })
  .then(() => console.log('MongoDB connected'))
  .catch(err => console.error('MongoDB connection error:', err));

// User Schema
const userSchema = new mongoose.Schema({
  username: { type: String, required: true, unique: true },
  email: { type: String, required: true, unique: true },
  password: { type: String, required: true },
  followers: [{ type: mongoose.Schema.Types.ObjectId, ref: 'User' }],
  following: [{ type: mongoose.Schema.Types.ObjectId, ref: 'User' }],
  followRequests: [{ type: mongoose.Schema.Types.ObjectId, ref: 'User' }]
});

const User = mongoose.model('User', userSchema);

// Helper function to get user data without password
const getUserData = (user) => {
  const userData = user.toObject();
  delete userData.password;
  return userData;
};

// Routes
// Register new user
app.post('/api/register', async (req, res) => {
  try {
    const { username, email, password } = req.body;
    
    // Check if user already exists
    const existingUser = await User.findOne({ $or: [{ email }, { username }] });
    if (existingUser) {
      return res.status(400).json({ message: 'User already exists' });
    }
    
    // Create new user
    const newUser = new User({ username, email, password }); // In production, hash the password
    await newUser.save();
    
    res.status(201).json({ message: 'User registered successfully', user: getUserData(newUser) });
  } catch (error) {
    res.status(500).json({ message: 'Server error', error: error.message });
  }
});

// Login user
app.post('/api/login', async (req, res) => {
  try {
    const { email, password } = req.body;
    
    // Find user by email
    const user = await User.findOne({ email });
    if (!user) {
      return res.status(400).json({ message: 'Invalid credentials' });
    }
    
    // In production, compare hashed passwords
    if (user.password !== password) {
      return res.status(400).json({ message: 'Invalid credentials' });
    }
    
    res.json({ message: 'Login successful', user: getUserData(user) });
  } catch (error) {
    res.status(500).json({ message: 'Server error', error: error.message });
  }
});

// Get user profile
app.get('/api/users/:id', async (req, res) => {
  try {
    const user = await User.findById(req.params.id).populate('followers following', 'username');
    if (!user) {
      return res.status(404).json({ message: 'User not found' });
    }
    
    res.json(getUserData(user));
  } catch (error) {
    res.status(500).json({ message: 'Server error', error: error.message });
  }
});

// Follow a user
app.post('/api/users/:id/follow', async (req, res) => {
  try {
    const userIdToFollow = req.params.id;
    const currentUser = req.body.currentUserId; // In real app, this would come from JWT token
    
    // Check if user is trying to follow themselves
    if (userIdToFollow === currentUser) {
      return res.status(400).json({ message: 'You cannot follow yourself' });
    }
    
    // Update both users' records
    await Promise.all([
      User.findByIdAndUpdate(currentUser, { $addToSet: { following: userIdToFollow } }),
      User.findByIdAndUpdate(userIdToFollow, { $addToSet: { followers: currentUser } })
    ]);
    
    res.json({ message: 'Successfully followed user' });
  } catch (error) {
    res.status(500).json({ message: 'Server error', error: error.message });
  }
});

// Unfollow a user
app.delete('/api/users/:id/unfollow', async (req, res) => {
  try {
    const userIdToUnfollow = req.params.id;
    const currentUser = req.body.currentUserId; // In real app, this would come from JWT token
    
    // Update both users' records
    await Promise.all([
      User.findByIdAndUpdate(currentUser, { $pull: { following: userIdToFollow } }),
      User.findByIdAndUpdate(userIdToUnfollow, { $pull: { followers: currentUser } })
    ]);
    
    res.json({ message: 'Successfully unfollowed user' });
  } catch (error) {
    res.status(500).json({ message: 'Server error', error: error.message });
  }
});

// Get suggestions for users to follow
app.get('/api/suggestions', async (req, res) => {
  try {
    const currentUserId = req.query.currentUserId; // In real app, this would come from JWT token
    
    // Find users that current user is not following and is not themselves
    const suggestions = await User.find({
      _id: { $nin: [currentUserId], $ne: currentUserId }
    }).limit(10);
    
    res.json(suggestions.map(user => getUserData(user)));
  } catch (error) {
    res.status(500).json({ message: 'Server error', error: error.message });
  }
});

// Start server
const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});