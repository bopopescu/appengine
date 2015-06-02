//
//  KSRegistrationErrors.h
//  Keystone
//
// Created by borisv on 9/12/14.
// Copyright 2014 Google Inc. All rights reserved.
//


// Registration error domain
extern NSString * const kKSRegistrationErrorDomain;

// Registration error codes
enum {
  kKSRegistrationGenericErrorMinimum = 1,
  kKSRegistrationGenericErrorMaximum = 200,

  kKSRegistrationNotImplementedError = 1,
  kKSRegistrationProductIDNotSetError = 2,
};


