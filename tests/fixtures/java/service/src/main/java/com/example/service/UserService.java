package com.example.service;

import java.util.HashMap;
import java.util.Map;

/** Stores and retrieves users. */
public class UserService {
    private final Map<Long, User> users = new HashMap<>();

    public User find(long id) {
        return users.get(id);
    }

    public User save(User user) {
        users.put(user.id(), user);
        return user;
    }
}
