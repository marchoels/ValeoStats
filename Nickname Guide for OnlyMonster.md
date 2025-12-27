# 🎯 Nickname Feature - Quick Guide

## ✅ What's New:

Now you can give your models **friendly names** instead of showing IDs!

---

## 📝 How to Use:

### Linking with Nicknames:

```
/link onlyfans 454315739 agency Maxes
/link onlyfans 987654321 agency Candi
/link onlyfans 123456789 agency Anabel
```

**Format:**
```
/link <platform> <account_id> <agency|chatter> <Nickname>
```

**Nickname can be multiple words:**
```
/link onlyfans 454315739 agency Hot Maxes
```

---

## 📊 What Shows Up:

### Before (without nicknames):
```
📊 Today's Revenue

Breakdown by Model:

🎯 454315739:
   💰 $1,176.20 | 👥 8 subs
```

### After (with nicknames):
```
📊 Today's Revenue

Breakdown by Model:

🎯 Maxes:
   💰 $1,176.20 | 👥 8 subs
```

Much cleaner! 🎉

---

## 🔍 Using Nicknames in Commands:

You can now use nicknames OR IDs:

```
/today Maxes      ← Uses nickname
/today 454315739  ← Uses ID (still works!)
```

Both work!

---

## 🔄 Examples:

### Setup for 3 Models:

```
/link onlyfans 454315739 agency Maxes
/link onlyfans 987654321 agency Candi  
/link onlyfans 123456789 agency Anabel
```

### Check Specific Model:

```
/today Maxes
/today Candi
/today Anabel
```

### Check All Models:

```
/today
```

Shows:
```
📊 Today's Revenue (1 AM - Now)

**All Models Combined:**
💰 Total Revenue: $4,567.89
👥 New Subscribers: 35

**Breakdown by Model:**

🎯 Maxes:
   💰 $1,500.00 | 👥 12 subs

🎯 Candi:
   💰 $2,000.50 | 👥 15 subs

🎯 Anabel:
   💰 $1,067.39 | 👥 8 subs
```

---

## ⚙️ Optional - You Don't Have to Use Nicknames

If you don't provide a nickname, it uses the ID:

```
/link onlyfans 454315739 agency
```

Will show `454315739` everywhere (like before)

---

## 🔄 Migration from Old Setup:

Your existing links will keep working!

**Old format (still works):**
```
/link onlyfans 454315739 agency
```

**New format (with nickname):**
```
/link onlyfans 454315739 agency Maxes
```

---

## 📋 Full Setup Example:

### Agency Group:
```
/link onlyfans 454315739 agency Maxes
/link onlyfans 987654321 agency Candi
/link onlyfans 123456789 agency Anabel
/link onlyfans 555666777 agency Ally
```

### Chatter Group (for Maxes):
```
/link onlyfans 454315739 chatter Maxes
```

---

## 💡 Pro Tips:

1. **Keep nicknames short** - "Maxes" is better than "Maxes OnlyFans Model"
2. **Use the same nickname** across all groups for consistency
3. **Case doesn't matter** - `/today maxes` and `/today Maxes` both work

---

## 🚀 How to Update:

1. Stop your bot (Ctrl+C)
2. Replace `bot.py` with the new version
3. Restart: `python3 bot.py`
4. Test with: `/link onlyfans 454315739 agency Maxes`

Done! 🎉
