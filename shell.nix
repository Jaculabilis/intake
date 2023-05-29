{ pkgs ? import <nixpkgs> {} }:

let
  intake = import ./default.nix {};
in pkgs.mkShell {
  inputsFrom = [ intake ];
  buildInputs = [ pkgs.nixos-shell ];
}
