// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/**
 * @title AccessControl
 * @notice Role-based access control for the Traffic Digital Twin.
 *         Enforces who can submit TLS commands, publish data,
 *         and audit the system.
 *
 * @dev   Roles:
 *        - ADMIN      : manage roles, intersections, policies
 *        - AI_AGENT   : submit TLS decisions to registered intersections
 *        - PUBLISHER  : publish/anchor traffic data on-chain
 *        - AUDITOR    : query full decision history (read-only, no on-chain gate)
 */
contract AccessControl {

    // ----------------------------------------------------------------
    // Role Definitions (keccak256 hashes for gas-efficient comparison)
    // ----------------------------------------------------------------
    bytes32 public constant ROLE_ADMIN     = keccak256("ADMIN");
    bytes32 public constant ROLE_AI_AGENT  = keccak256("AI_AGENT");
    bytes32 public constant ROLE_PUBLISHER = keccak256("PUBLISHER");
    bytes32 public constant ROLE_AUDITOR   = keccak256("AUDITOR");

    // ----------------------------------------------------------------
    // State
    // ----------------------------------------------------------------
    address public superAdmin;

    // role => address => granted
    mapping(bytes32 => mapping(address => bool)) private _roles;

    // Registered intersection IDs
    mapping(string => bool) public registeredIntersections;
    string[] public intersectionList;

    // ----------------------------------------------------------------
    // Events
    // ----------------------------------------------------------------
    event RoleGranted(bytes32 indexed role, address indexed account, address indexed granter);
    event RoleRevoked(bytes32 indexed role, address indexed account, address indexed revoker);
    event IntersectionRegistered(string intersectionId);
    event IntersectionRemoved(string intersectionId);
    event CommandValidated(address indexed agent, string intersection, bool allowed);

    // ----------------------------------------------------------------
    // Modifiers
    // ----------------------------------------------------------------
    modifier onlyAdmin() {
        require(
            _roles[ROLE_ADMIN][msg.sender] || msg.sender == superAdmin,
            "AccessControl: caller is not an admin"
        );
        _;
    }

    // ----------------------------------------------------------------
    // Constructor
    // ----------------------------------------------------------------
    constructor() {
        superAdmin = msg.sender;
        _roles[ROLE_ADMIN][msg.sender] = true;
        emit RoleGranted(ROLE_ADMIN, msg.sender, msg.sender);
    }

    // ----------------------------------------------------------------
    // Role Management
    // ----------------------------------------------------------------
    function grantRole(bytes32 role, address account) external onlyAdmin {
        _roles[role][account] = true;
        emit RoleGranted(role, account, msg.sender);
    }

    function revokeRole(bytes32 role, address account) external onlyAdmin {
        _roles[role][account] = false;
        emit RoleRevoked(role, account, msg.sender);
    }

    function hasRole(bytes32 role, address account) external view returns (bool) {
        return _roles[role][account];
    }

    // ----------------------------------------------------------------
    // Intersection Registry
    // ----------------------------------------------------------------
    function registerIntersection(string memory intersectionId) external onlyAdmin {
        require(!registeredIntersections[intersectionId], "Already registered");
        registeredIntersections[intersectionId] = true;
        intersectionList.push(intersectionId);
        emit IntersectionRegistered(intersectionId);
    }

    function removeIntersection(string memory intersectionId) external onlyAdmin {
        require(registeredIntersections[intersectionId], "Not registered");
        registeredIntersections[intersectionId] = false;
        emit IntersectionRemoved(intersectionId);
    }

    function isRegisteredIntersection(string memory intersectionId) external view returns (bool) {
        return registeredIntersections[intersectionId];
    }

    function getIntersectionCount() external view returns (uint256) {
        return intersectionList.length;
    }

    // ----------------------------------------------------------------
    // Validation Functions
    // ----------------------------------------------------------------

    /**
     * @notice Validate whether a sender can issue a TLS command
     *         to a specific intersection.
     * @return allowed True if sender has AI_AGENT role AND intersection is registered.
     */
    function validateCommand(
        address sender,
        string memory intersection
    ) external returns (bool allowed) {
        allowed = _roles[ROLE_AI_AGENT][sender] && registeredIntersections[intersection];
        emit CommandValidated(sender, intersection, allowed);
        return allowed;
    }

    /**
     * @notice Validate whether a sender can publish/anchor data.
     * @return True if sender has PUBLISHER role.
     */
    function validatePublisher(address sender) external view returns (bool) {
        return _roles[ROLE_PUBLISHER][sender];
    }

    /**
     * @notice Validate whether a sender can audit decision history.
     * @return True if sender has AUDITOR role.
     */
    function validateAuditor(address sender) external view returns (bool) {
        return _roles[ROLE_AUDITOR][sender];
    }
}
