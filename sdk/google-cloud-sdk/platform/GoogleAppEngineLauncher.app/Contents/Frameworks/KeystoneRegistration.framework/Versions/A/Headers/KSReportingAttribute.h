// Copyright 2014 Google Inc.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

#import <Cocoa/Cocoa.h>

// Reporting attributes allow Keystone managed applications to pass simple usage
// data to the update server during the update pings. A good example is the number
// of signed in users. The application may specify an unsigned attribute with name
// "numSigned" and set it to 1 to indicate the presence of 1 signed in user.
// The application may also specify for how long Keystone should keep reporting
// this value. E.g. Chrome may want to keep this attribute for 28 days (default lifetime).
// The clock starts ticking when the attribute is created (see expirationDate_ field).
// Keystone will be sending the attribute with the update checks for the next 28 days.
// If the user doesn't run Chrome for more than 28 days, Chrome will not update this
// attribute. After the 28 day lifetime expires, Keystone will stop reporting this
// attribute when sending an update check ping.
// In addition to the expiration, system Keystone may build ability to support
// aggregation of the values across multiple users, so that the total value for
// the machine is reported. This ability works only if the Keystone ticket is
// system-level and not user-level.
//
// Sample usage:
// KSRegistration *reg = ...;
// KSError *error = nil;
// KSUnsignedReportingAttribute *attr = [KSUnsignedReportingAttribute
//    reportingAttributeWithValue:numProfiles
//                           name:@"numProfiles"
//                aggregationType:kKSReportingAggregationSum
//                          error:&error];
// if (attr) {
//   [reg setActiveWithReportingAttributes:[NSArray arrayWithObject:attr]
//                                   error:&error];
// }

// Supported aggregation methods. Used in the system Keystone to calculate the
// reporting attribute value, when the value is reported by multiple users.
// E.g. if "sum" is used, the values are simply added. Summation is suitable for
// numerable values like "number of ...", but not for proprotional ones like
// "percent of profiles signed in during the last session".
typedef enum {
  kKSReportingAggregationSum = 0,  // Adds attribute value across user accounts
  kKSReportingAggregationDefault = kKSReportingAggregationSum,
} KSReportingAggregationType;

// KSReportingAttribute
//
// Holds generic reporting attribute properties.
// The class is not thread-safe.
@interface KSReportingAttribute : NSObject {
 @protected
  // The name of the reporting attribute. Should be alphanumeric
  // with no white space. May contain '_'. See setName method.
  NSString *name_;

  // Holds the value of the attribute
  id<NSObject> value_;

  // The point of time when the attribute will expire and the update engine will
  // stop reporting it to update server.
  NSDate *expirationDate_;

  // In the case of system ticket, this value controls the way in which the
  // attribute values are going to be aggregated.
  KSReportingAggregationType aggregationType_;
}

// Serializes the attributes to a dictionary.
+ (NSMutableDictionary *)encodeReportingAttributes:(NSArray *)attributes
                                             error:(NSError **)error;

// Persists the reporting attributes
+ (BOOL)saveReportingAttributes:(NSArray *)attributes
                         toFile:(NSString *)filePath
                          error:(NSError **)error;

// Reads the attributes from a file.
+ (NSArray *)decodeReportingAttributesFromFile:(NSString *)filePath
                                         error:(NSError **)error;

// Given a dictionary with the contents of attributes, the method instantiates and initializes the
// attributes
+ (NSArray *)decodeReportingAttributesFromDictionary:(NSDictionary *)attributesContents
                                               error:(NSError **)error;

// The amount of time the attribute will continue to be reported.
- (NSTimeInterval)lifetime;
- (BOOL)setLifetime:(NSTimeInterval)lifetime error:(NSError **)error;

// The exact point of time when the attribute will expire and update engine will stop
// reporting it to the update server.
- (NSDate *)expirationDate;
- (BOOL)setExpirationDate:(NSDate *)date error:(NSError **)error;

// The method returns the value stored, as a generic NSObject. Derived classes
// accessors provide a more specific data type.
- (id<NSObject>)value;

// The value of the attribute as a string. Default implementation uses 'description'
// selector of the value. Derived classes may extend it to provide a more human readable
// form. Used in the 'description' method and when passing the attribute value to in the
// XML payload to the update server.
- (NSString *)stringValue;

// The name of the attribute. setName checks that the name starts with a letter or '_'
// and contains only Latin letters, digits and '_', '-'. If the attribute does not
// start with '_', an '_' will be added by this method. Thus, we ensure that the attributes
// do not collide with important pre-set attributes like "version" or "OS". The name is
// case-insensitive and is stored as lowercase.
- (NSString *)name;
- (BOOL)setName:(NSString *)name error:(NSError **)error;

// Confirms if a name is correct. Typically called by setName and helper methods.
// See "setName" for definition of "correctness".
+ (BOOL)verifyAttributeName:(NSString *)name error:(NSError **)error;

// Aggregates the values across multiple attributes. Generates a single aggregated attribute
// to hold the value on success. Returns nil if the |attributes| is nil or empty. If the
// attribute type does not support aggregation, the first attribute is returned. This behavior
// is used by the update engine to ensure that the first attribute is the one for the current
// user. Thus, if the system Keystone is engaged and the non-aggregatable attribute is reported
// by multiple users, only the current user attribute will be reported to the update server.
+ (KSReportingAttribute *)aggregateWithAttributes:(NSArray *)attributes error:(NSError **)error;

@end

// The class holds a single custom reporting attribute of type unsigned integer
// that the application would like to be pass during the uddate server ping.
@interface KSUnsignedReportingAttribute : KSReportingAttribute

// Creates the attribute using default lifetime
+ (KSUnsignedReportingAttribute *)reportingAttributeWithValue:(uint32_t)value
                                                         name:(NSString *)name
                                              aggregationType:
                                                  (KSReportingAggregationType)aggregationType
                                                        error:(NSError **)error;

// Adds ability to specify the lifetime of the attribute as an interval since now:
+ (KSUnsignedReportingAttribute *)reportingAttributeWithValue:(uint32_t)value
                                                         name:(NSString *)name
                                              aggregationType:
                                                  (KSReportingAggregationType)aggregationType
                                                     lifetime:(NSTimeInterval)lifetime
                                                        error:(NSError **)error;

// Specifies an explicit expiration date:
+ (KSUnsignedReportingAttribute *)reportingAttributeWithValue:(uint32_t)value
                                                         name:(NSString *)name
                                              aggregationType:
                                                  (KSReportingAggregationType)aggregationType
                                               expirationDate:(NSDate *)expirationDate
                                                        error:(NSError **)error;

// Get/set the value of the attribute as "unsigned int"
- (uint32_t)unsignedIntValue;
- (void)setUnsignedIntValue:(uint32_t)value;

- (KSReportingAggregationType)aggregationType;
- (void)setAggregationType:(KSReportingAggregationType)aggregationType;

@end
